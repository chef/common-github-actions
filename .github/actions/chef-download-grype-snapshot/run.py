import os, json, subprocess, re
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

def env(k, d=""):
    return os.environ.get(k, d)

def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def run(cmd, check=True):
    p = subprocess.run(cmd, text=True, capture_output=True)
    if check and p.returncode != 0:
        raise RuntimeError(f"Command failed: {cmd}\nstdout:\n{p.stdout}\nstderr:\n{p.stderr}")
    return p.returncode, p.stdout.strip(), p.stderr.strip()

def http_json(url):
    rc, out, err = run(["bash", "-lc", f"curl -fsSL '{url}'"], check=True)
    return json.loads(out)

def ensure_dir(path):
    run(["bash","-lc", f"mkdir -p '{path}'"], check=True)

def write_text(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

# Inputs
product       = env("PRODUCT")
channel       = env("CHANNEL")
download_site = env("DOWNLOAD_SITE", "commercial")
os_name       = env("OS", "ubuntu")
os_ver        = env("OS_VERSION")
arch          = env("ARCH", "x86_64")
scan_mode     = env("SCAN_MODE", "native")
scan_root     = env("SCAN_ROOT", "")
resolve_ver   = env("RESOLVE_VERSION", "latest")
pinned_ver    = env("PINNED_VERSION", "")
license_id    = env("LICENSE_ID", "")
out_dir       = env("OUT_DIR", "out")
work_dir      = env("WORK_DIR", "work")


# Guard: commercial downloads require a license_id (fail fast with a clear error)
if download_site == "commercial" and not license_id.strip():
    raise RuntimeError(
        "Commercial download_site requires LICENSE_ID, but it was empty. "
        "Fix by scoping GA_DOWNLOAD_GRYPE_LICENSE_ID to the orchestrator repo and passing it into the composite action, "
        "or switch DOWNLOAD_SITE to 'community' for targets that do not require licensing."
    )

ensure_dir(out_dir)
ensure_dir(work_dir)

# Choose base URL
base = "https://chefdownload-commercial.chef.io" if download_site == "commercial" else "https://chefdownload-community.chef.io"

# Resolve version
resolved_version = pinned_ver
if resolve_ver == "latest" or not resolved_version:
    # Note: Community downloads may not support /versions/latest endpoint or may require different auth
    # Try fetching latest version; if it fails, we'll need to fallback or error clearly
    ver_url = f"{base}/{channel}/{product}/versions/latest"
    if download_site == "commercial" and license_id:
        ver_url += f"?license_id={license_id}"
    
    try:
        ver_doc = http_json(ver_url)
        if isinstance(ver_doc, dict):
            resolved_version = (
                ver_doc.get("version")
                or ver_doc.get("latest")
                or ver_doc.get("artifact_version")
                or ver_doc.get("value")
            )
            if not resolved_version:
                resolved_version = str(ver_doc)
        else:
            resolved_version = str(ver_doc)
    except RuntimeError as e:
        if "403" in str(e) or "401" in str(e):
            raise RuntimeError(
                f"Failed to fetch version from {ver_url.split('?')[0]} (status 403/401).\n"
                f"This may indicate:\n"
                f"  1. The '{download_site}' download site requires authentication even for version lookup\n"
                f"  2. The product '{product}' or channel '{channel}' doesn't exist or isn't accessible\n"
                f"  3. For 'community' site: the /versions/latest endpoint may not be supported\n"
                f"Solution: Either provide a PINNED_VERSION in targets.yml or switch DOWNLOAD_SITE to 'commercial' with a valid LICENSE_ID"
            ) from e
        raise

# Construct download URL
download_url = f"{base}/{channel}/{product}/download?p={os_name}&pv={os_ver}&m={arch}&v={resolved_version}"
if download_site == "commercial" and license_id:
    download_url += f"&license_id={license_id}"

# Redact license_id (robust URL parsing)
parts = urlsplit(download_url)
q = [(k,v) for (k,v) in parse_qsl(parts.query, keep_blank_values=True) if k != "license_id"]
download_url_redacted = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q, doseq=True), parts.fragment))

# Persist small values for action outputs
write_text(os.path.join(out_dir, "_resolved_version.txt"), resolved_version)
write_text(os.path.join(out_dir, "_download_url_redacted.txt"), download_url_redacted)

# Download package
pkg_path = os.path.join(work_dir, "package_downloaded.deb")
run(["bash","-lc", f"curl -fsSL -o '{pkg_path}' '{download_url}'"], check=True)

# Extract deterministically (pilot assumes Ubuntu .deb)
extract_dir = os.path.join(work_dir, "extracted")
run(["bash","-lc", f"rm -rf '{extract_dir}' && mkdir -p '{extract_dir}'"], check=True)
run(["bash","-lc", f"dpkg-deb -x '{pkg_path}' '{extract_dir}'"], check=True)

# Ensure grype
run(["bash","-lc", "command -v grype >/dev/null 2>&1 || (curl -sSfL https://get.anchore.io/grype | sh -s -- -b /usr/local/bin)"], check=True)

# Run grype scan to JSON (do not print findings to stdout)
latest_json_path = os.path.join(out_dir, "latest.json")
run(["bash","-lc", f"grype dir:'{extract_dir}' --name '{product}' --output json > '{latest_json_path}'"], check=True)

# Parse counts and rewrite with pretty formatting
doc = json.load(open(latest_json_path, "r", encoding="utf-8"))
json.dump(doc, open(latest_json_path, "w", encoding="utf-8"), indent=2)
doc = json.load(open(latest_json_path, "r", encoding="utf-8"))
matches = doc.get("matches", []) or []

buckets = ["Critical","High","Medium","Low","Negligible","Unknown"]
sev_counts = {k: 0 for k in buckets}

for m in matches:
    sev = (m.get("vulnerability", {}) or {}).get("severity", "Unknown") or "Unknown"
    sev_norm = sev.strip().title()
    if sev_norm in ("Negligible","Minimal"):
        sev_norm = "Negligible"
    if sev_norm not in sev_counts:
        sev_norm = "Unknown"
    sev_counts[sev_norm] += 1

# Grype version + DB status (best effort)
grype_version = ""
rc, out, err = run(["bash","-lc", "grype version"], check=False)
if rc == 0:
    m = re.search(r"Version:\s*([0-9]+\.[0-9]+\.[0-9]+(?:[-+.\w]+)?)", out)
    if m:
        grype_version = m.group(1)

db_info = {}
rc, out, err = run(["bash","-lc", "grype db status -o json"], check=False)
if rc == 0 and out.startswith("{"):
    try:
        dbj = json.loads(out)
        db_info["status_raw"] = dbj
        for k in ("built","builtAt","lastBuilt","updated","updatedAt","lastUpdated"):
            if k in dbj:
                db_info["built_utc"] = dbj.get(k)
                break
        for k in ("schemaVersion","schema","dbSchemaVersion"):
            if k in dbj:
                db_info["schema"] = dbj.get(k)
                break
        for k in ("checksum","hash","etag"):
            if k in dbj:
                db_info["checksum"] = dbj.get(k)
                break
    except Exception:
        db_info["status_raw_text"] = out
else:
    rc2, out2, err2 = run(["bash","-lc","grype db status"], check=False)
    if rc2 == 0:
        db_info["status_raw_text"] = out2
        m = re.search(r"(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z)", out2)
        if m:
            db_info["built_utc"] = m.group(1)

# Metadata
gha_run_id = env("GITHUB_RUN_ID", "")
repo = env("GITHUB_REPOSITORY", "")
workflow = env("GITHUB_WORKFLOW", "")
sha = env("GITHUB_SHA", "")

metadata = {
    "schema_version": "1.0",
    "snapshot": {
        "timestamp_utc": now_utc(),
        "run_id": f"gha-{gha_run_id}" if gha_run_id else "",
        "pipeline": {"repo": repo, "workflow": workflow, "git_sha": sha}
    },
    "target": {
        "product": product,
        "channel": channel,
        "resolved_version": resolved_version,
        "download": {"site": download_site, "url_redacted": download_url_redacted}
    },
    "environment": {
        "runner": env("RUNNER_OS",""),
        "os": os_name,
        "os_version": os_ver,
        "arch": arch
    },
    "scan": {
        "mode": scan_mode,
        "scan_root": scan_root,
        "grype": {"version": grype_version, "db": db_info},
        "options": {"output": "json"}
    },
    "summary": {
        "matches_total": len(matches),
        "severity_counts": sev_counts
    }
}

metadata_path = os.path.join(out_dir, "metadata.json")
json.dump(metadata, open(metadata_path, "w", encoding="utf-8"), indent=2)
print("Wrote:", latest_json_path, metadata_path)