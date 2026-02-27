import os, json, subprocess, re, time, random
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

def env(k, d=""):
    return os.environ.get(k, d)

def now_utc():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

def run(cmd, check=True, retry_config=None):
    """
    Execute command with optional retry logic.
    
    Args:
        cmd: Command to execute
        check: Raise on non-zero exit
        retry_config: Dict with retry settings (if None, no retry)
                     {"max_retries": 5, "base_delay": 2, "max_delay": 30}
    """
    if retry_config is None:
        # No retry - original behavior
        p = subprocess.run(cmd, text=True, capture_output=True)
        if check and p.returncode != 0:
            raise RuntimeError(f"Command failed: {cmd}\nstdout:\n{p.stdout}\nstderr:\n{p.stderr}")
        return p.returncode, p.stdout.strip(), p.stderr.strip()
    
    # Retry logic
    max_retries = retry_config.get("max_retries", 5)
    base_delay = retry_config.get("base_delay", 2)
    max_delay = retry_config.get("max_delay", 30)
    
    last_error = None
    for attempt in range(max_retries):
        p = subprocess.run(cmd, text=True, capture_output=True)
        
        if p.returncode == 0:
            return p.returncode, p.stdout.strip(), p.stderr.strip()
        
        last_error = f"Command failed: {cmd}\nstdout:\n{p.stdout}\nstderr:\n{p.stderr}"
        
        # Check if error is retryable
        if not is_retryable_error(p.stderr, p.stdout):
            if check:
                raise RuntimeError(last_error)
            return p.returncode, p.stdout.strip(), p.stderr.strip()
        
        # Calculate backoff with jitter
        if attempt < max_retries - 1:  # Don't sleep on last attempt
            jitter = random.uniform(0, 1)
            sleep_time = min((base_delay * (2 ** attempt)) + jitter, max_delay)
            print(f"⚠️  Retryable error on attempt {attempt + 1}/{max_retries}")
            print(f"   Error: {p.stderr.strip()[:200]}")
            print(f"   Retrying in {sleep_time:.1f}s...")
            time.sleep(sleep_time)
    
    # All retries exhausted
    if check:
        raise RuntimeError(f"Failed after {max_retries} attempts: {last_error}")
    return p.returncode, p.stdout.strip(), p.stderr.strip()

def is_retryable_error(stderr, stdout):
    """
    Determine if error is retryable based on curl error codes and messages.
    
    Retryable errors:
    - (92) HTTP/2 stream errors
    - (18) Partial file transfer
    - (56) Failure receiving network data
    - (7) Failed to connect
    - (28) Timeout
    - (52) Empty reply from server
    - (55) Failed sending network data
    
    Non-retryable errors:
    - 400, 401, 403, 404 (client errors)
    """
    error_text = stderr.lower() + stdout.lower()
    
    # Retryable curl error codes
    retryable_codes = [
        "(92)",  # HTTP/2 stream error - THE MAIN ISSUE
        "(18)",  # Partial file
        "(56)",  # Recv error
        "(7)",   # Failed to connect
        "(28)",  # Timeout
        "(52)",  # Empty reply
        "(55)",  # Send error
        "(16)",  # HTTP/2 error
    ]
    
    for code in retryable_codes:
        if code in error_text:
            return True
    
    # Check for HTTP server errors (5xx)
    if any(code in error_text for code in ["500", "502", "503", "504"]):
        return True
    
    # Non-retryable conditions
    if any(code in error_text for code in ["401", "403", "404", "400"]):
        return False
    
    # Default: don't retry unless explicitly identified as retryable
    return False

def http_json(url):
    rc, out, err = run(["bash", "-lc", f"curl -fsSL '{url}'"], check=True)
    return json.loads(out)

def parse_version(version_str):
    """
    Parse a semantic version string into comparable components.
    
    Args:
        version_str: Version string (e.g., "5.24.7", "6.8.24")
        
    Returns:
        Tuple of (major, minor, patch) as integers, or None if parsing fails
    """
    if not version_str:
        return None
    
    # Remove any 'v' prefix
    clean_ver = version_str.strip().lstrip('v')
    
    # Split on dots and take first 3 components
    parts = clean_ver.split('.')
    
    try:
        major = int(parts[0]) if len(parts) > 0 else 0
        minor = int(parts[1]) if len(parts) > 1 else 0
        
        # Handle patch version (may have additional text like "7-rc1")
        patch = 0
        if len(parts) > 2:
            # Extract numeric part only
            patch_str = parts[2].split('-')[0].split('+')[0]
            patch = int(patch_str) if patch_str.isdigit() else 0
        
        return (major, minor, patch)
    except (ValueError, IndexError):
        return None

def get_major_version(version_str):
    """
    Extract the major version number from a version string.
    
    Args:
        version_str: Version string (e.g., "5.24.7")
        
    Returns:
        Major version as integer, or None if parsing fails
    """
    parsed = parse_version(version_str)
    return parsed[0] if parsed else None

def find_best_stable_version_for_major(all_stable_versions, target_major):
    """
    Find the highest stable version matching a specific major version.
    
    Args:
        all_stable_versions: List of version strings from stable channel
        target_major: Target major version number (int)
        
    Returns:
        Highest matching version string, or None if no match found
    """
    matching_versions = []
    
    for ver_str in all_stable_versions:
        parsed = parse_version(ver_str)
        if parsed and parsed[0] == target_major:
            matching_versions.append((parsed, ver_str))
    
    if not matching_versions:
        return None
    
    # Sort by (major, minor, patch) tuple - highest last
    matching_versions.sort(key=lambda x: x[0])
    
    # Return the version string of the highest match
    return matching_versions[-1][1]

def ensure_dir(path):
    run(["bash","-lc", f"mkdir -p '{path}'"], check=True)

def write_text(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)

def get_directory_size(path):
    """
    Calculate the total size of all files in a directory (recursively).
    
    Args:
        path: Directory path to calculate size for
        
    Returns:
        Dictionary with size information:
        - bytes: Total size in bytes
        - human_readable: Human-readable size string (e.g., "1.5 GB")
        - file_count: Number of files
    """
    total_size = 0
    file_count = 0
    
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                try:
                    # Use lstat to not follow symlinks (avoid double-counting)
                    total_size += os.lstat(filepath).st_size
                    file_count += 1
                except (OSError, FileNotFoundError):
                    # Skip files we can't stat (permissions, removed during walk, etc.)
                    pass
        
        # Format human-readable size
        size_bytes = total_size
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0 or unit == 'TB':
                human_readable = f"{size_bytes:.2f} {unit}"
                break
            size_bytes = size_bytes / 1024.0
            
        # Return original bytes value
        return {
            "bytes": total_size,
            "human_readable": human_readable,
            "file_count": file_count
        }
    except Exception as e:
        print(f"Warning: Error calculating directory size for {path}: {e}")
        return {
            "bytes": 0,
            "human_readable": "0 B",
            "file_count": 0,
            "error": str(e)
        }

def download_with_fallback(url, output_path, timeout=300):
    """
    Download file with HTTP/2 fallback to HTTP/1.1 and retry logic.
    
    This addresses the curl (92) HTTP/2 stream errors by:
    1. Trying HTTP/2 first with retries
    2. Falling back to HTTP/1.1 if HTTP/2 consistently fails
    3. Using exponential backoff with jitter
    """
    print(f"Downloading: {output_path}")
    print(f"URL (redacted): {url.split('?')[0]}...")
    
    # HTTP version strategies to try in order
    http_strategies = [
        {
            "name": "HTTP/2",
            "flags": ["--http2"],
            "retries": 3  # Try HTTP/2 3 times before falling back
        },
        {
            "name": "HTTP/1.1",
            "flags": ["--http1.1"],
            "retries": 5  # Try HTTP/1.1 more times as fallback
        }
    ]
    
    retry_config = {
        "max_retries": 5,
        "base_delay": 2,
        "max_delay": 30
    }
    
    last_error = None
    
    for strategy in http_strategies:
        print(f"Attempting download with {strategy['name']}...")
        
        for attempt in range(strategy["retries"]):
            try:
                cmd = [
                    "bash", "-lc",
                    " ".join([
                        "curl",
                        "-fsSL",
                        *strategy["flags"],
                        "--connect-timeout", "30",
                        "--max-time", str(timeout),
                        "--keepalive-time", "60",
                        "--tcp-nodelay",
                        "--compressed",
                        "-o", f"'{output_path}'",
                        f"'{url}'"
                    ])
                ]
                
                # Execute with retry logic
                run(cmd, check=True, retry_config=retry_config)
                
                # Verify download
                if os.path.exists(output_path):
                    size = os.path.getsize(output_path)
                    print(f"✓ Download successful ({size} bytes) using {strategy['name']}")
                    return True
                else:
                    raise RuntimeError(f"Download completed but file not found: {output_path}")
                
            except RuntimeError as e:
                last_error = e
                error_str = str(e)
                
                # Check if this is a protocol error specific to current HTTP version
                if "(92)" in error_str or "http/2" in error_str.lower():
                    print(f"✗ {strategy['name']} protocol error, will try fallback strategy")
                    break  # Move to next HTTP version
                elif not is_retryable_error(error_str, ""):
                    # Non-retryable error, fail immediately
                    print(f"✗ Non-retryable error: {error_str[:200]}")
                    raise
                else:
                    # Retryable error, continue with current strategy
                    if attempt < strategy["retries"] - 1:
                        jitter = random.uniform(0, 1)
                        sleep_time = min(2 ** attempt + jitter, 30)
                        print(f"⚠️  Attempt {attempt + 1}/{strategy['retries']} failed, retrying in {sleep_time:.1f}s...")
                        time.sleep(sleep_time)
                    else:
                        print(f"✗ All {strategy['retries']} attempts with {strategy['name']} failed")
                        break  # Try next strategy
    
    # All strategies exhausted
    raise RuntimeError(
        f"Download failed after all retry strategies:\n"
        f"  URL: {url.split('?')[0]}\n"
        f"  Last error: {last_error}"
    )

def map_cinc_product_name(product):
    """
    Map Chef product names to CINC product names for API endpoints.
    CINC (Cinc Is Not Chef) uses different package names.
    """
    cinc_mapping = {
        "chef": "cinc",
        "chef-server": "cinc-server",
        "chef-workstation": "cinc-workstation",
        "inspec": "cinc-auditor"
    }
    return cinc_mapping.get(product, product)

def check_existing_version(scan_mode, data_repo_path, product, channel, download_site, os_name, os_ver, arch, resolved_version=None, hab_ident=None):
    """
    Check if existing scan data matches the resolved version.
    Returns (should_skip, reason) tuple.
    For native mode: checks metadata.json in native/ path
    For modern mode: checks metadata.json in modern/ path
    For habitat mode: checks index.json and extracts version from directory structure
    """
    if not data_repo_path or not os.path.exists(data_repo_path):
        return False, "No existing data repository found"
    
    try:
        if scan_mode == "native":
            # Native mode: check metadata.json
            metadata_path = os.path.join(
                data_repo_path,
                "native",
                product,
                channel,
                download_site,
                os_name,
                os_ver,
                arch,
                "metadata.json"
            )
            
            if os.path.exists(metadata_path):
                with open(metadata_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                existing_version = metadata.get("target", {}).get("resolved_version", "")
                
                print(f"Version comparison: existing='{existing_version}' vs resolved='{resolved_version}'")
                if existing_version == resolved_version:
                    return True, f"Version {resolved_version} already scanned (found in metadata.json)"
                else:
                    return False, f"Version mismatch: existing={existing_version}, resolved={resolved_version}"
            
            return False, "No existing metadata found"
        
        elif scan_mode == "habitat":
            # Habitat mode: check for existing version directory under habitat/{product}/{channel}/{os}/{arch}/
            # Structure: habitat/{product}/{channel}/{os}/{arch}/{origin}/{name}/{version}/index.json
            hab_base_path = os.path.join(
                data_repo_path,
                "habitat",
                product,
                channel,
                os_name,
                arch
            )
            
            if not os.path.exists(hab_base_path):
                return False, "No existing habitat data found"
            
            # Parse hab_ident to get origin/name for path lookup
            # Expected format: origin/name or origin/name/version/release
            if hab_ident:
                parts = hab_ident.split("/")
                if len(parts) >= 2:
                    origin, name = parts[0], parts[1]
                    origin_name_path = os.path.join(hab_base_path, origin, name)
                    
                    if os.path.exists(origin_name_path):
                        # Get list of existing version directories
                        existing_versions = [d for d in os.listdir(origin_name_path) 
                                           if os.path.isdir(os.path.join(origin_name_path, d))]
                        
                        # Check if any existing version has an index.json with matching version
                        for version_dir in existing_versions:
                            index_path = os.path.join(origin_name_path, version_dir, "index.json")
                            if os.path.exists(index_path):
                                with open(index_path, "r", encoding="utf-8") as f:
                                    index = json.load(f)
                                existing_ident = index.get("target", {}).get("package", {}).get("ident", "")
                                
                                # Compare full ident (origin/name/version/release)
                                if resolved_version and existing_ident == resolved_version:
                                    return True, f"Habitat package {resolved_version} already scanned (found in index.json)"
            
            return False, "No existing habitat scan or version mismatch"
        
        elif scan_mode == "modern":
            # Modern mode: check metadata.json (same as native but under modern/ path)
            metadata_path = os.path.join(
                data_repo_path,
                "modern",
                product,
                channel,
                download_site,
                os_name,
                os_ver,
                arch,
                "metadata.json"
            )
            
            if os.path.exists(metadata_path):
                with open(metadata_path, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
                existing_version = metadata.get("target", {}).get("resolved_version", "")
                
                print(f"Version comparison: existing='{existing_version}' vs resolved='{resolved_version}'")
                if existing_version == resolved_version:
                    return True, f"Version {resolved_version} already scanned (found in metadata.json)"
                else:
                    return False, f"Version mismatch: existing={existing_version}, resolved={resolved_version}"
            
            return False, "No existing metadata found"
    
    except Exception as e:
        print(f"Warning: Error checking existing version: {e}")
        return False, f"Error checking existing version: {e}"
    
    return False, "Unknown check result"

# Inputs
product       = env("PRODUCT")
channel       = env("CHANNEL")
download_site = env("DOWNLOAD_SITE", "commercial")
os_name       = env("OS", "ubuntu")
os_ver        = env("OS_VERSION", "")
arch          = env("ARCH", "x86_64")
package_manager = env("PACKAGE_MANAGER", "")
scan_mode     = env("SCAN_MODE", "native")
scan_root     = env("SCAN_ROOT", "")
resolve_ver   = env("RESOLVE_VERSION", "latest")
pinned_ver    = env("PINNED_VERSION", "")
license_id    = env("LICENSE_ID", "")
base_url_override = env("BASE_URL_OVERRIDE", "")
out_dir       = env("OUT_DIR", "out")
work_dir      = env("WORK_DIR", "work")
data_repo_path = env("DATA_REPO_PATH", "")
full_product_scan = env("FULL_PRODUCT_SCAN", "false").lower() in ("true", "1", "yes")
hab_ident     = env("HAB_IDENT", "")
hab_channel   = env("HAB_CHANNEL", "stable")
hab_origin    = env("HAB_ORIGIN", "")
hab_auth_token = env("HAB_AUTH_TOKEN", "")
enable_trivy  = env("ENABLE_TRIVY", "true").lower() in ("true", "1", "yes")
trivy_scanners = env("TRIVY_SCANNERS", "vuln")
trivy_severity = env("TRIVY_SEVERITY", "UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL")
trivy_ignore_unfixed = env("TRIVY_IGNORE_UNFIXED", "false").lower() in ("true", "1", "yes")
trivy_timeout = env("TRIVY_TIMEOUT", "")
trivy_cache_dir = env("TRIVY_CACHE_DIR", "")

ensure_dir(out_dir)
ensure_dir(work_dir)

# Create scanners output directory (for native/modern mode)
if scan_mode in ["native", "modern"]:
    scanners_dir = os.path.join(out_dir, "scanners")
    ensure_dir(scanners_dir)

# Branch based on scan_mode
if scan_mode == "habitat":
    # HABITAT MODE: Install hab package, enumerate deps, scan each separately
    
    # Guard: habitat mode requires hab_ident or hab_origin
    if not hab_ident.strip() and not hab_origin.strip():
        raise RuntimeError(
            "Habitat scan_mode requires HAB_IDENT (e.g., 'core/chef-infra-client') or HAB_ORIGIN (e.g., 'chef'). "
            "Set one in the target configuration."
        )
    
    # Ensure hab CLI is available
    run(["bash", "-lc", "command -v hab >/dev/null 2>&1 || (curl -fsSL https://raw.githubusercontent.com/habitat-sh/habitat/master/components/hab/install.sh | sudo bash)"], check=True)
    
    # Accept the Chef License for Habitat (CI environment - create marker file for root)
    run(["bash", "-lc", "sudo mkdir -p /hab/accepted-licenses && sudo touch /hab/accepted-licenses/habitat"], check=True)
    
    # Determine package identifier
    pkg_to_install = hab_ident if hab_ident else f"{hab_origin}/{product}"
    
    # Install the package (with channel if specified) - requires sudo for /hab/pkgs/ access
    # Note: Chef packages now require HAB_AUTH_TOKEN even for stable channel
    install_cmd = f"sudo hab pkg install {pkg_to_install}"
    if hab_channel and hab_channel != "stable":
        install_cmd += f" --channel {hab_channel}"
    
    # Set HAB_AUTH_TOKEN if provided (required for protected packages including chef/* in stable)
    if hab_auth_token:
        if hab_channel and hab_channel != "stable":
            install_cmd = f"sudo HAB_AUTH_TOKEN={hab_auth_token} hab pkg install {pkg_to_install} --channel {hab_channel}"
        else:
            install_cmd = f"sudo HAB_AUTH_TOKEN={hab_auth_token} hab pkg install {pkg_to_install}"
    
    run(["bash", "-lc", install_cmd], check=True)
    
    # Get installed package details
    rc, out, err = run(["bash", "-lc", f"sudo hab pkg path {pkg_to_install}"], check=True)
    installed_path = out.strip()
    
    # Parse origin/name/version/release from path
    # Expected: /hab/pkgs/<origin>/<name>/<version>/<release> or C:\hab\pkgs\<origin>\<name>\<version>\<release>
    path_parts = installed_path.replace("\\", "/").split("/")
    if len(path_parts) >= 4:
        origin, name, version, release = path_parts[-4:]
        resolved_version = f"{origin}/{name}/{version}/{release}"
    else:
        raise RuntimeError(f"Unable to parse habitat package path: {installed_path}")
    
    # Check if this version is already scanned (unless full_product_scan is enabled)
    if not full_product_scan:
        should_skip, skip_reason = check_existing_version(
            scan_mode="habitat",
            data_repo_path=data_repo_path,
            product=product,
            channel=hab_channel,
            download_site="",  # Not used for habitat
            os_name=os_name,
            os_ver=os_ver,
            arch=arch,
            resolved_version=resolved_version,
            hab_ident=hab_ident
        )
        
        if should_skip:
            print(f"SKIP: {skip_reason}")
            print(f"::debug::Skipping habitat scan for {product} {hab_channel}: {skip_reason}")
            # Write minimal outputs for workflow to continue
            write_text(os.path.join(out_dir, "_resolved_version.txt"), resolved_version)
            write_text(os.path.join(out_dir, "_download_url_redacted.txt"), f"habitat://{resolved_version}@{hab_channel}")
            write_text(os.path.join(out_dir, "_skipped.txt"), "true")
            exit(0)
    else:
        print(f"INFO: Full product scan enabled - bypassing version check")

    
    # Enumerate direct dependencies (from DEPS file)
    main_ident = f"{origin}/{name}/{version}/{release}"
    deps_file = f"{installed_path}/DEPS"
    rc, out, err = run(["bash", "-lc", f"sudo cat {deps_file} 2>/dev/null || echo ''"], check=False)
    if rc == 0 and out.strip():
        direct_dep_idents = [line.strip() for line in out.split("\n") if line.strip() and "/" in line]
    else:
        direct_dep_idents = []
    
    # Enumerate transitive dependencies (full tree - includes direct deps per Habitat definition)
    rc, out, err = run(["bash", "-lc", f"sudo hab pkg dependencies -t {pkg_to_install}"], check=True)
    transitive_dep_idents = [line.strip() for line in out.split("\n") if line.strip() and "/" in line and line.strip() != main_ident]
    
    # Build combined list for scanning: main package + direct deps + all transitive deps
    # Note: Direct deps will be scanned twice (once in direct-deps/, once in transitive-deps/)
    # Tag each with its type for proper directory placement
    deps_to_scan = [
        {"ident": main_ident, "type": "main"},
    ]
    for ident in direct_dep_idents:
        deps_to_scan.append({"ident": ident, "type": "direct"})
    for ident in transitive_dep_idents:
        deps_to_scan.append({"ident": ident, "type": "transitive"})
    
    # Ensure grype (may be restored from cache)
    grype_version = os.getenv("GRYPE_VERSION", "0.109.0")
    if os.path.isfile("/usr/local/bin/grype"):
        # Ensure executable permissions (cache may not preserve them)
        run(["chmod", "+x", "/usr/local/bin/grype"], check=False)
        print("✓ Grype found in cache")
    else:
        rc, _, _ = run(["bash", "-lc", "command -v grype >/dev/null 2>&1"], check=False)
        if rc == 0:
            print("✓ Grype already installed")
        else:
            # Install with retry logic for GitHub releases API
            print(f"Installing Grype {grype_version}...")
            install_cmd = f"curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh | sh -s -- -b /usr/local/bin v{grype_version}"
            run(["bash", "-lc", install_cmd], check=True, retry_config={"max_retries": 5, "base_delay": 2, "max_delay": 30})
    
    # Create main package directory structure: {origin}/{name}/{version}/
    main_pkg_dir = os.path.join(out_dir, origin, name, version)
    ensure_dir(main_pkg_dir)
    
    # Log what we're scanning
    print(f"Habitat scan: {main_ident}")
    print(f"Channel: {hab_channel}")
    print(f"Total dependencies to scan: {len(deps_to_scan)}")
    print(f"  - Main package: 1")
    print(f"  - Direct dependencies: {len(direct_dep_idents)}")
    print(f"  - Transitive dependencies: {len(transitive_dep_idents)}")
    
    # Scan each dependency separately
    dep_results = []
    
    for dep_info in deps_to_scan:
        dep_ident = dep_info["ident"]
        dep_type = dep_info["type"]
        # Parse dependency ident: origin/name/version/release
        dep_parts = dep_ident.split("/")
        if len(dep_parts) != 4:
            print(f"Skipping malformed dependency ident: {dep_ident}")
            continue
        
        dep_origin, dep_name, dep_version, dep_release = dep_parts
        
        # Determine scan path
        if os_name == "windows":
            dep_scan_path = f"C:\\hab\\pkgs\\{dep_origin}\\{dep_name}\\{dep_version}\\{dep_release}"
        else:
            dep_scan_path = f"/hab/pkgs/{dep_origin}/{dep_name}/{dep_version}/{dep_release}"
        
        # Determine output location based on dependency type
        if dep_type == "main":
            # Main package files go directly in main_pkg_dir
            dep_out_dir = main_pkg_dir
        elif dep_type == "direct":
            # Direct dependencies go under direct-deps/{origin}/{name}/{version}/
            dep_out_dir = os.path.join(main_pkg_dir, "direct-deps", dep_origin, dep_name, dep_version)
        else:  # transitive
            # Transitive dependencies go under transitive-deps/{origin}/{name}/{version}/
            dep_out_dir = os.path.join(main_pkg_dir, "transitive-deps", dep_origin, dep_name, dep_version)
        
        ensure_dir(dep_out_dir)
        
        dep_json_path = os.path.join(dep_out_dir, f"{dep_release}.json")
        dep_metadata_path = os.path.join(dep_out_dir, f"{dep_release}.metadata.json")
        
        # Calculate installed size for this Habitat package
        dep_size = get_directory_size(dep_scan_path)
        
        # Run grype scan
        try:
            run(["bash", "-lc", f"grype dir:'{dep_scan_path}' --name '{dep_ident}' --output json > '{dep_json_path}'"], check=True)
            
            # Parse and pretty-print
            dep_doc = json.load(open(dep_json_path, "r", encoding="utf-8"))
            json.dump(dep_doc, open(dep_json_path, "w", encoding="utf-8"), indent=2)
            
            # Count vulnerabilities by severity
            dep_matches = dep_doc.get("matches", []) or []
            buckets = ["Critical", "High", "Medium", "Low", "Negligible", "Unknown"]
            dep_sev_counts = {k: 0 for k in buckets}
            
            for m in dep_matches:
                sev = (m.get("vulnerability", {}) or {}).get("severity", "Unknown") or "Unknown"
                sev_norm = sev.strip().title()
                if sev_norm in ("Negligible", "Minimal"):
                    sev_norm = "Negligible"
                if sev_norm not in dep_sev_counts:
                    sev_norm = "Unknown"
                dep_sev_counts[sev_norm] += 1
            
            # Create per-dependency metadata
            dep_metadata = {
                "schema_version": "1.0",
                "dependency": {
                    "ident": dep_ident,
                    "origin": dep_origin,
                    "name": dep_name,
                    "version": dep_version,
                    "release": dep_release,
                    "scan_path": dep_scan_path,
                    "size": {
                        "installed_bytes": dep_size["bytes"],
                        "installed_human_readable": dep_size["human_readable"],
                        "file_count": dep_size["file_count"]
                    }
                },
                "scan": {
                    "timestamp_utc": now_utc(),
                    "matches_total": len(dep_matches),
                    "severity_counts": dep_sev_counts
                }
            }
            json.dump(dep_metadata, open(dep_metadata_path, "w", encoding="utf-8"), indent=2)
            
            # Track for rollup
            # Build json_path based on dependency type
            if dep_type == "main":
                json_rel_path = f"{dep_release}.json"
            elif dep_type == "direct":
                json_rel_path = f"direct-deps/{dep_origin}/{dep_name}/{dep_version}/{dep_release}.json"
            else:  # transitive
                json_rel_path = f"transitive-deps/{dep_origin}/{dep_name}/{dep_version}/{dep_release}.json"
            
            dep_results.append({
                "ident": dep_ident,
                "origin": dep_origin,
                "name": dep_name,
                "version": dep_version,
                "release": dep_release,
                "matches_total": len(dep_matches),
                "severity_counts": dep_sev_counts,
                "json_path": json_rel_path,
                "dependency_type": dep_type,
                "size": {
                    "installed_bytes": dep_size["bytes"],
                    "installed_human_readable": dep_size["human_readable"],
                    "file_count": dep_size["file_count"]
                }
            })
            
            print(f"Scanned dependency: {dep_ident} - {dep_size['human_readable']} ({len(dep_matches)} matches)")
            
        except Exception as e:
            print(f"Failed to scan dependency {dep_ident}: {e}")
            # Continue with other dependencies
    
    # Create index.json rollup
    # Grype version + DB status
    grype_version = ""
    rc, out, err = run(["bash", "-lc", "grype version"], check=False)
    if rc == 0:
        m = re.search(r"Version:\s*([0-9]+\.[0-9]+\.[0-9]+(?:[-+.\w]+)?)", out)
        if m:
            grype_version = m.group(1)
    
    db_info = {}
    rc, out, err = run(["bash", "-lc", "grype db status -o json"], check=False)
    if rc == 0 and out.startswith("{"):
        try:
            dbj = json.loads(out)
            db_info["status_raw"] = dbj
            for k in ("built", "builtAt", "lastBuilt", "updated", "updatedAt", "lastUpdated"):
                if k in dbj:
                    db_info["built_utc"] = dbj.get(k)
                    break
            for k in ("schemaVersion", "schema", "dbSchemaVersion"):
                if k in dbj:
                    db_info["schema"] = dbj.get(k)
                    break
            for k in ("checksum", "hash", "etag"):
                if k in dbj:
                    db_info["checksum"] = dbj.get(k)
                    break
        except Exception:
            db_info["status_raw_text"] = out
    
    # Calculate aggregate counts
    total_matches = sum(d["matches_total"] for d in dep_results)
    aggregate_counts = {k: 0 for k in ["Critical", "High", "Medium", "Low", "Negligible", "Unknown"]}
    for d in dep_results:
        for sev, count in d["severity_counts"].items():
            aggregate_counts[sev] += count
    
    # Calculate aggregate size (total disk footprint of all dependencies)
    total_size_bytes = sum(d.get("size", {}).get("installed_bytes", 0) for d in dep_results)
    total_file_count = sum(d.get("size", {}).get("file_count", 0) for d in dep_results)
    
    # Format aggregate size
    size_bytes = total_size_bytes
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size_bytes < 1024.0 or unit == 'TB':
            total_size_human = f"{size_bytes:.2f} {unit}"
            break
        size_bytes = size_bytes / 1024.0
    
    # GitHub Actions context
    gha_run_id = env("GITHUB_RUN_ID", "")
    repo = env("GITHUB_REPOSITORY", "")
    workflow = env("GITHUB_WORKFLOW", "")
    sha = env("GITHUB_SHA", "")
    
    index = {
        "schema_version": "1.0",
        "snapshot": {
            "timestamp_utc": now_utc(),
            "run_id": f"gha-{gha_run_id}" if gha_run_id else "",
            "pipeline": {"repo": repo, "workflow": workflow, "git_sha": sha}
        },
        "target": {
            "product": product,
            "channel": hab_channel,
            "package": {
                "ident": main_ident,
                "origin": origin,
                "name": name,
                "version": version,
                "release": release
            },
            "size": {
                "total_installed_bytes": total_size_bytes,
                "total_installed_human_readable": total_size_human,
                "total_file_count": total_file_count
            }
        },
        "environment": {
            "runner": env("RUNNER_OS", ""),
            "os": os_name,
            "os_version": os_ver,
            "arch": arch
        },
        "scan": {
            "mode": "habitat",
            "grype": {"version": grype_version, "db": db_info}
        },
        "summary": {
            "dependencies_scanned": len(dep_results),
            "total_matches": total_matches,
            "aggregate_severity_counts": aggregate_counts
        },
        "dependencies": dep_results
    }
    
    # Write index.json in the main package directory
    index_path = os.path.join(main_pkg_dir, "index.json")
    json.dump(index, open(index_path, "w", encoding="utf-8"), indent=2)
    
    # Write resolved_version for workflow outputs (keep in out_dir root for workflow to find)
    write_text(os.path.join(out_dir, "_resolved_version.txt"), resolved_version)
    write_text(os.path.join(out_dir, "_download_url_redacted.txt"), f"habitat://{main_ident}@{hab_channel}")
    
    print(f"Wrote habitat index: {index_path}")
    print(f"Scanned {len(dep_results)} dependencies with {total_matches} total matches")
    print(f"Total installed size: {total_size_human} ({total_file_count:,} files)")
    print(f"::notice::✓ Habitat scan completed for {product} {hab_channel}: {main_ident} with {len(dep_results)} dependencies ({total_matches} total vulnerabilities, {total_size_human} disk footprint)")

else:
    # NATIVE/MODERN MODE: Download + extract + scan logic
    # (modern mode is identical to native but uses /modern/ path for next-gen products)
    
    # Guard: commercial downloads require a license_id (fail fast with a clear error)
    # CINC downloads don't require license_id
    if download_site == "commercial" and not license_id.strip():
        raise RuntimeError(
            "Commercial download_site requires LICENSE_ID, but it was empty. "
            "Fix by scoping GA_DOWNLOAD_GRYPE_LICENSE_ID to the orchestrator repo and passing it into the composite action, "
            "or switch DOWNLOAD_SITE to 'community' for targets that do not require licensing."
        )
    
    # Map product name for CINC downloads (chef -> cinc, inspec -> cinc-auditor, etc.)
    api_product = map_cinc_product_name(product) if download_site == "cinc" else product
    
    # Choose base URL (support override for alternative download sites)
    if base_url_override:
        base = base_url_override.rstrip("/")
        print(f"Using base URL override: {base}")
    elif download_site == "cinc":
        base = "https://omnitruck.cinc.sh"
    else:
        base = "https://chefdownload-commercial.chef.io" if download_site == "commercial" else "https://chefdownload-community.chef.io"

    # Resolve version
    resolved_version = pinned_ver
    if resolve_ver == "latest" or not resolved_version:
        # For stable channel, implement major version matching logic
        # to ensure we compare stable against the same major version as current
        if channel == "stable":
            try:
                print("🔍 Major version matching enabled for stable channel")
                
                # Step 1: Get the latest version from current channel
                current_ver_url = f"{base}/current/{api_product}/versions/latest"
                if license_id and download_site != "cinc":
                    current_ver_url += f"?license_id={license_id}"
                
                print(f"Fetching current channel latest: {current_ver_url.split('?')[0]}{'?license_id=***' if license_id and download_site != 'cinc' else ''}")
                current_ver_doc = http_json(current_ver_url)
                
                current_version = None
                if isinstance(current_ver_doc, dict):
                    current_version = (
                        current_ver_doc.get("version")
                        or current_ver_doc.get("latest")
                        or current_ver_doc.get("artifact_version")
                        or current_ver_doc.get("value")
                    )
                    if not current_version:
                        current_version = str(current_ver_doc)
                else:
                    current_version = str(current_ver_doc).strip().strip('"')
                
                print(f"Current channel latest version: {current_version}")
                
                # Step 2: Extract major version from current
                current_major = get_major_version(current_version)
                
                if current_major is not None:
                    print(f"Current channel major version: {current_major}")
                    
                    # Step 3: Get all stable versions
                    stable_all_url = f"{base}/stable/{api_product}/versions/all"
                    if license_id and download_site != "cinc":
                        stable_all_url += f"?license_id={license_id}"
                    
                    print(f"Fetching all stable versions: {stable_all_url.split('?')[0]}{'?license_id=***' if license_id and download_site != 'cinc' else ''}")
                    stable_all_versions = http_json(stable_all_url)
                    
                    if isinstance(stable_all_versions, list) and stable_all_versions:
                        print(f"Found {len(stable_all_versions)} stable versions")
                        
                        # Step 4: Find the best matching version in stable
                        best_stable = find_best_stable_version_for_major(stable_all_versions, current_major)
                        
                        if best_stable:
                            print(f"✅ Best stable version matching major {current_major}: {best_stable}")
                            resolved_version = best_stable
                        else:
                            print(f"⚠️  No stable version found matching major {current_major}, falling back to /latest")
                            # Fall back to regular latest logic below
                            resolved_version = None
                    else:
                        print(f"⚠️  Could not fetch stable versions list, falling back to /latest")
                        resolved_version = None
                else:
                    print(f"⚠️  Could not parse major version from current ({current_version}), falling back to /latest")
                    resolved_version = None
                    
            except Exception as e:
                print(f"⚠️  Major version matching failed: {e}")
                print(f"   Falling back to standard /latest endpoint")
                resolved_version = None
        
        # Fall back to standard /latest logic if major version matching was skipped or failed
        if not resolved_version:
            ver_url = f"{base}/{channel}/{api_product}/versions/latest"
            # Commercial and community require license_id, but CINC does not
            if license_id and download_site != "cinc":
                ver_url += f"?license_id={license_id}"
            
            print(f"Fetching latest version from: {ver_url.split('?')[0]}{'?license_id=***' if license_id and download_site != 'cinc' else ''}")
            try:
                ver_doc = http_json(ver_url)
                print(f"API response type: {type(ver_doc).__name__}")
                print(f"API response value: {ver_doc}")
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
                    resolved_version = str(ver_doc).strip().strip('"')
            except RuntimeError as e:
                error_msg = str(e)
                # CINC doesn't require licenses, so skip license-specific error handling
                if download_site != "cinc" and ("403" in error_msg or "401" in error_msg or "Missing license_id" in error_msg or "License Id is not valid" in error_msg or "Only Free license" in error_msg):
                    site_type = "commercial" if download_site == "commercial" else "community"
                    license_secret = "GA_DOWNLOAD_GRYPE_LICENSE_ID" if download_site == "commercial" else "GA_DOWNLOAD_GRYPE_LICENSE_ID_FREE"
                    
                    if "Missing license_id" in error_msg:
                        raise RuntimeError(
                            f"LICENSE ERROR ({site_type}): Missing license_id parameter.\n"
                            f"  Download site: {download_site}\n"
                            f"  Required secret: {license_secret}\n"
                            f"  Solution: Ensure the {license_secret} secret is set in the orchestrator repository"
                        ) from e
                    elif "License Id is not valid" in error_msg or "403" in error_msg:
                        raise RuntimeError(
                            f"LICENSE ERROR ({site_type}): Invalid or expired license_id.\n"
                            f"  Download site: {download_site}\n"
                            f"  Product: {product}, Channel: {channel}\n"
                            f"  Secret used: {license_secret}\n"
                            f"  Solution: Update the {license_secret} secret with a valid {'commercial' if download_site == 'commercial' else 'Free'} license"
                        ) from e
                    elif "Only Free license" in error_msg:
                        raise RuntimeError(
                            f"LICENSE ERROR (community): Wrong license type provided.\n"
                            f"  Download site: community\n"
                            f"  Error: Community downloads require a 'Free' license, but a commercial license was provided\n"
                            f"  Solution: Update GA_DOWNLOAD_GRYPE_LICENSE_ID_FREE secret with a valid Free license (not commercial)"
                        ) from e
                    else:
                        raise RuntimeError(
                            f"LICENSE ERROR ({site_type}): Authentication failed.\n"
                            f"  Download site: {download_site}\n"
                            f"  Product: {product}, Channel: {channel}\n"
                            f"  Secret used: {license_secret}\n"
                            f"  Solution: Verify the {license_secret} secret contains a valid license for {download_site} downloads"
                        ) from e
                raise

    print(f"Resolved version: '{resolved_version}' (type: {type(resolved_version).__name__})")
    
    # Check if this version is already scanned (unless full_product_scan is enabled)
    if not full_product_scan:
        should_skip, skip_reason = check_existing_version(
            scan_mode=scan_mode,
            data_repo_path=data_repo_path,
            product=product,
            channel=channel,
            download_site=download_site,
            os_name=os_name,
            os_ver=os_ver,
            arch=arch,
            resolved_version=resolved_version,
            hab_ident=None
        )
        
        if should_skip:
            print(f"SKIP: {skip_reason}")
            print(f"::debug::Skipping {scan_mode} scan for {product} {channel} ({download_site}): {skip_reason}")
            # Write minimal outputs for workflow to continue
            write_text(os.path.join(out_dir, "_resolved_version.txt"), resolved_version)
            # Construct redacted URL for output
            if download_site == "cinc":
                # For CINC, construct a descriptive URL (actual URL would require fetching packages endpoint)
                download_url_redacted = f"{base}/{channel}/{api_product}/packages (Platform: {os_name}/{os_ver}/{arch})"
            else:
                q_params = [("p", os_name), ("m", arch), ("v", resolved_version)]
                if os_ver:
                    q_params.insert(1, ("pv", os_ver))
                if package_manager:
                    q_params.insert(2, ("pm", package_manager))
                parts = urlsplit(f"{base}/{channel}/{api_product}/download")
                download_url_redacted = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q_params, doseq=True), parts.fragment))
            write_text(os.path.join(out_dir, "_download_url_redacted.txt"), download_url_redacted)
            write_text(os.path.join(out_dir, "_skipped.txt"), "true")
            exit(0)
    else:
        print(f"INFO: Full product scan enabled - bypassing version check")


    # Construct download URL
    # Support three patterns:
    # 1. Standard Chef: ?p=ubuntu&pv=24.04&m=x86_64&v=latest (commercial/community)
    # 2. Universal binaries: ?p=linux&pm=deb&m=x86_64&v=latest (chef-ice - no pv parameter)
    # 3. CINC: Fetch from /packages endpoint and extract direct .deb URL
    
    if download_site == "cinc":
        # CINC provides direct package URLs via /packages endpoint
        packages_url = f"{base}/{channel}/{api_product}/packages"
        print(f"Fetching CINC package info from: {packages_url}")
        
        try:
            packages_doc = http_json(packages_url)
            # Navigate: packages_doc[os][os_version][arch]["url"]
            if os_name in packages_doc and os_ver in packages_doc[os_name] and arch in packages_doc[os_name][os_ver]:
                pkg_info = packages_doc[os_name][os_ver][arch]
                download_url = pkg_info.get("url", "")
                if not download_url:
                    raise RuntimeError(f"No URL found in CINC package info for {os_name}/{os_ver}/{arch}")
                
                # Verify version matches
                pkg_version = pkg_info.get("version", "")
                if pkg_version and pkg_version != resolved_version:
                    print(f"Warning: Package version {pkg_version} differs from resolved version {resolved_version}")
            else:
                raise RuntimeError(
                    f"CINC package not found for platform combination.\n"
                    f"  Product: {api_product} (Chef: {product})\n"
                    f"  OS: {os_name} {os_ver}, Arch: {arch}\n"
                    f"  Available in packages: {list(packages_doc.keys())}"
                )
        except RuntimeError as e:
            if "CINC package not found" in str(e):
                raise
            raise RuntimeError(
                f"Failed to fetch CINC package information.\n"
                f"  Product: {api_product} (Chef: {product})\n"
                f"  URL: {packages_url}\n"
                f"  Error: {str(e)}"
            ) from e
        
        download_url_redacted = download_url  # CINC URLs don't contain secrets
    else:
        # Chef commercial/community pattern
        download_url = f"{base}/{channel}/{api_product}/download?p={os_name}"
        if os_ver:  # Optional for universal binaries
            download_url += f"&pv={os_ver}"
        download_url += f"&m={arch}"
        if package_manager:  # Required for universal binaries like chef-ice
            download_url += f"&pm={package_manager}"
        download_url += f"&v={resolved_version}"
        if license_id:
            download_url += f"&license_id={license_id}"

        # Redact license_id (robust URL parsing)
        parts = urlsplit(download_url)
        q = [(k,v) for (k,v) in parse_qsl(parts.query, keep_blank_values=True) if k != "license_id"]
        download_url_redacted = urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(q, doseq=True), parts.fragment))

    # Persist small values for action outputs
    write_text(os.path.join(out_dir, "_resolved_version.txt"), resolved_version)
    write_text(os.path.join(out_dir, "_download_url_redacted.txt"), download_url_redacted)

    # Log what we're downloading
    print(f"Downloading {product} {channel} version {resolved_version}")
    print(f"Download URL: {download_url_redacted}")
    print(f"Target: {os_name}{'/' + os_ver if os_ver else ''}/{arch}{'/' + package_manager if package_manager else ''}")

    # Download package with resilient retry logic
    pkg_path = os.path.join(work_dir, "package_downloaded.deb")
    try:
        # Use new download_with_fallback function with HTTP/2 → HTTP/1.1 fallback
        download_with_fallback(download_url, pkg_path, timeout=300)
        print(f"Downloaded package: {os.path.getsize(pkg_path)} bytes")
    except RuntimeError as e:
        if "500" in str(e):
            raise RuntimeError(
                f"DOWNLOAD ERROR: Server error (500) when downloading {product}.\n"
                f"  Product: {product} v{resolved_version}\n"
                f"  Channel: {channel}, OS: {os_name} {os_ver}, Arch: {arch}\n"
                f"  Package manager: {package_manager or 'N/A'}\n"
                f"  Download site: {download_site}\n"
                f"  This may indicate:\n"
                f"    1. Channel '{channel}' doesn't exist for this product\n"
                f"    2. Server-side error with Chef downloads infrastructure\n"
                f"  Solution: Verify the channel is available for this product, or try again later"
            ) from e
        elif "403" in str(e) or "401" in str(e):
            if download_site == "cinc":
                raise RuntimeError(
                    f"DOWNLOAD ERROR (CINC): Failed to download package.\n"
                    f"  Product: {product} ({api_product}) v{resolved_version}\n"
                    f"  Channel: {channel}, OS: {os_name} {os_ver}\n"
                    f"  This may indicate:\n"
                    f"    1. Package not available for this OS/version combination\n"
                    f"    2. Version {resolved_version} doesn't exist in {channel} channel\n"
                    f"  Solution: Verify that the product/version/platform combination is valid"
                ) from e
            else:
                site_type = "commercial" if download_site == "commercial" else "community"
                license_secret = "GA_DOWNLOAD_GRYPE_LICENSE_ID" if download_site == "commercial" else "GA_DOWNLOAD_GRYPE_LICENSE_ID_FREE"
                raise RuntimeError(
                    f"DOWNLOAD ERROR ({site_type}): Failed to download package.\n"
                    f"  Product: {product} v{resolved_version}\n"
                    f"  Channel: {channel}, OS: {os_name} {os_ver}\n"
                    f"  Download site: {download_site}\n"
                    f"  This may indicate:\n"
                    f"    1. Invalid or expired {license_secret} secret\n"
                    f"    2. Package not available for this OS/version combination\n"
                    f"    3. Version {resolved_version} doesn't exist in {channel} channel\n"
                    f"  Solution: Verify license and that the product/version/platform combination is valid"
                ) from e
        raise

    # Validate downloaded file
    if not os.path.exists(pkg_path):
        raise RuntimeError(f"Download failed: package file not found at {pkg_path}")
    
    file_size = os.path.getsize(pkg_path)
    if file_size < 1024:  # Less than 1KB is likely an error page or empty file
        raise RuntimeError(
            f"DOWNLOAD ERROR: Downloaded file is suspiciously small ({file_size} bytes).\n"
            f"  Product: {product} v{resolved_version}\n"
            f"  Channel: {channel}, Download site: {download_site}\n"
            f"  This indicates an incomplete or corrupted download.\n"
            f"  Solution: Check network connectivity and retry. If issue persists, the package may not exist for this platform."
        )
    
    # Verify it's a valid debian package by checking for debian-binary member
    rc, out, err = run(["bash","-lc", f"ar t '{pkg_path}' 2>/dev/null | grep -q 'debian-binary' && echo 'valid' || echo 'invalid'"], check=False)
    if out.strip() != "valid":
        raise RuntimeError(
            f"DOWNLOAD ERROR: Downloaded file is not a valid Debian package.\n"
            f"  Product: {product} v{resolved_version}\n"
            f"  Channel: {channel}, Download site: {download_site}\n"
            f"  File size: {file_size} bytes\n"
            f"  This indicates a corrupted download or an error page was returned instead of the package.\n"
            f"  Solution: Retry the download. If issue persists, check if the package exists for this platform."
        )
    
    print(f"Downloaded package: {file_size} bytes")

    # Extract deterministically (pilot assumes Ubuntu .deb)
    extract_dir = os.path.join(work_dir, "extracted")
    run(["bash","-lc", f"rm -rf '{extract_dir}' && mkdir -p '{extract_dir}'"], check=True)
    
    try:
        run(["bash","-lc", f"dpkg-deb -x '{pkg_path}' '{extract_dir}'"], check=True)
    except RuntimeError as e:
        raise RuntimeError(
            f"EXTRACTION ERROR: Failed to extract Debian package.\n"
            f"  Product: {product} v{resolved_version}\n"
            f"  Channel: {channel}, Download site: {download_site}\n"
            f"  File size: {file_size} bytes\n"
            f"  Error: {str(e)}\n"
            f"  This indicates a corrupted download or malformed package.\n"
            f"  Solution: The download will be retried on the next run. If issue persists, report to Chef support."
        ) from e

    # Handle nested bundle extraction for migration packages (e.g., chef-ice)
    # These packages contain a hab/migration/bundle/*.tar.gz with the actual software
    bundle_glob = os.path.join(extract_dir, "hab", "migration", "bundle", "*.tar.gz")
    rc, bundle_files, _ = run(["bash", "-lc", f"ls {bundle_glob} 2>/dev/null || true"], check=False)
    if bundle_files.strip():
        bundle_tarball = bundle_files.strip().split('\n')[0]  # Take first match
        print(f"Detected migration bundle package: {os.path.basename(bundle_tarball)}")
        print(f"Extracting nested Habitat package for scanning...")
        
        # Extract the bundle tarball into the extract_dir (will create hab/ structure)
        try:
            run(["bash", "-lc", f"tar -xzf '{bundle_tarball}' -C '{extract_dir}'"], check=True)
            print(f"✓ Successfully extracted nested bundle")
        except RuntimeError as e:
            raise RuntimeError(
                f"EXTRACTION ERROR: Failed to extract nested migration bundle.\n"
                f"  Product: {product} v{resolved_version}\n"
                f"  Bundle: {os.path.basename(bundle_tarball)}\n"
                f"  This is a migration package (e.g., chef-ice) with nested Habitat content.\n"
                f"  Error: {str(e)}"
            ) from e

    # Calculate installed size (disk footprint after extraction)
    print(f"Calculating installed size...")
    installed_size = get_directory_size(extract_dir)
    print(f"Installed size: {installed_size['human_readable']} ({installed_size['file_count']} files)")

    # Ensure grype (may be restored from cache)
    grype_version = os.getenv("GRYPE_VERSION", "0.109.0")
    if os.path.isfile("/usr/local/bin/grype"):
        # Ensure executable permissions (cache may not preserve them)
        run(["chmod", "+x", "/usr/local/bin/grype"], check=False)
        print("✓ Grype found in cache")
    else:
        rc, _, _ = run(["bash","-lc", "command -v grype >/dev/null 2>&1"], check=False)
        if rc == 0:
            print("✓ Grype already installed")
        else:
            # Install with retry logic for GitHub releases API
            print(f"Installing Grype {grype_version}...")
            install_cmd = f"curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh | sh -s -- -b /usr/local/bin v{grype_version}"
            run(["bash","-lc", install_cmd], check=True, retry_config={"max_retries": 5, "base_delay": 2, "max_delay": 30})

    # Run grype scan to JSON (do not print findings to stdout)
    grype_latest_json = os.path.join(scanners_dir, "grype.latest.json")
    run(["bash","-lc", f"grype dir:'{extract_dir}' --name '{product}' --output json > '{grype_latest_json}'"], check=True)

    # Parse counts and rewrite with pretty formatting
    doc = json.load(open(grype_latest_json, "r", encoding="utf-8"))
    json.dump(doc, open(grype_latest_json, "w", encoding="utf-8"), indent=2)
    doc = json.load(open(grype_latest_json, "r", encoding="utf-8"))
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

    grype_metadata = {
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
            "download": {"site": download_site, "url_redacted": download_url_redacted},
            "size": {
                "package_bytes": file_size,
                "installed_bytes": installed_size["bytes"],
                "installed_human_readable": installed_size["human_readable"],
                "file_count": installed_size["file_count"]
            }
        },
        "environment": {
            "runner": env("RUNNER_OS",""),
            "os": os_name,
            "os_version": os_ver,
            "arch": arch,
            "package_manager": package_manager if package_manager else None
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

    grype_metadata_path = os.path.join(scanners_dir, "grype.metadata.json")
    json.dump(grype_metadata, open(grype_metadata_path, "w", encoding="utf-8"), indent=2)

    # Legacy compatibility: copy Grype files to out/ root
    import shutil
    shutil.copy2(grype_latest_json, os.path.join(out_dir, "latest.json"))
    shutil.copy2(grype_metadata_path, os.path.join(out_dir, "metadata.json"))

    print("Wrote Grype outputs:", grype_latest_json, grype_metadata_path)
    print(f"::notice::✓ {scan_mode.title()} scan completed for {product} {channel} v{resolved_version}: {len(matches)} vulnerabilities found (Critical: {sev_counts['Critical']}, High: {sev_counts['High']}, Medium: {sev_counts['Medium']})")

    # ============================================================================
    # TRIVY SCANNING
    # ============================================================================

    if enable_trivy:
        print("Running Trivy scan...")
        
        # Run Trivy filesystem scan
        trivy_latest_json = os.path.join(scanners_dir, "trivy.latest.json")
        trivy_cmd = f"trivy fs --format json --scanners {trivy_scanners} --severity {trivy_severity}"
        
        if trivy_ignore_unfixed:
            trivy_cmd += " --ignore-unfixed"
        if trivy_timeout:
            trivy_cmd += f" --timeout {trivy_timeout}"
        if trivy_cache_dir:
            trivy_cmd += f" --cache-dir '{trivy_cache_dir}'"
        
        trivy_cmd += f" '{extract_dir}' > '{trivy_latest_json}'"
        
        try:
            run(["bash", "-lc", trivy_cmd], check=True)
        except RuntimeError as e:
            print(f"WARNING: Trivy scan failed: {e}")
            # Write empty results on failure
            json.dump({"Results": [], "error": str(e)}, open(trivy_latest_json, "w", encoding="utf-8"), indent=2)
        
        # Parse Trivy results and pretty-print
        trivy_doc = json.load(open(trivy_latest_json, "r", encoding="utf-8"))
        json.dump(trivy_doc, open(trivy_latest_json, "w", encoding="utf-8"), indent=2)
        trivy_doc = json.load(open(trivy_latest_json, "r", encoding="utf-8"))
        
        # Extract vulnerability counts from Trivy results (handle missing Results)
        trivy_results = trivy_doc.get("Results", []) or []
        trivy_sev_counts = {k: 0 for k in ["Critical","High","Medium","Low","Negligible","Unknown"]}
        trivy_cves = set()
        
        for result in trivy_results:
            vulns = result.get("Vulnerabilities") or []
            for vuln in vulns:
                cve_id = vuln.get("VulnerabilityID", "")
                if cve_id:
                    trivy_cves.add(cve_id)
                
                sev = vuln.get("Severity", "Unknown") or "Unknown"
                sev_norm = sev.strip().upper()
                # Map Trivy severities to our buckets
                if sev_norm in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "UNKNOWN"):
                    trivy_sev_counts[sev_norm.title()] += 1
                elif sev_norm in ("NEGLIGIBLE", "MINIMAL"):
                    trivy_sev_counts["Negligible"] += 1
                else:
                    trivy_sev_counts["Unknown"] += 1
        
        # Get Trivy version and DB info
        trivy_version = ""
        trivy_db_info = {}
        
        rc, out, err = run(["bash", "-lc", "trivy --version"], check=False)
        if rc == 0:
            # Parse version output
            for line in out.split("\n"):
                if "Version:" in line:
                    m = re.search(r"Version:\s*([0-9]+\.[0-9]+\.[0-9]+(?:[-+.\w]+)?)", line)
                    if m:
                        trivy_version = m.group(1)
                elif "Vulnerability DB:" in line:
                    # Try to extract DB metadata from version output
                    if "Version:" in line:
                        m = re.search(r"Version:\s*(\d+)", line)
                        if m:
                            trivy_db_info["version"] = m.group(1)
                    if "UpdatedAt:" in line:
                        m = re.search(r"UpdatedAt:\s*([\d-]+T[\d:]+Z)", line)
                        if m:
                            trivy_db_info["updated_at"] = m.group(1)
                    if "NextUpdate:" in line:
                        m = re.search(r"NextUpdate:\s*([\d-]+T[\d:]+Z)", line)
                        if m:
                            trivy_db_info["next_update"] = m.group(1)
                    if "DownloadedAt:" in line:
                        m = re.search(r"DownloadedAt:\s*([\d-]+T[\d:]+Z)", line)
                        if m:
                            trivy_db_info["downloaded_at"] = m.group(1)
        
        # Build Trivy metadata
        trivy_metadata = {
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
                "download": {"site": download_site, "url_redacted": download_url_redacted},
                "size": {
                    "package_bytes": file_size,
                    "installed_bytes": installed_size["bytes"],
                    "installed_human_readable": installed_size["human_readable"],
                    "file_count": installed_size["file_count"]
                }
            },
            "environment": {
                "runner": env("RUNNER_OS",""),
                "os": os_name,
                "os_version": os_ver,
                "arch": arch,
                "package_manager": package_manager if package_manager else None
            },
            "scan": {
                "mode": scan_mode,
                "scan_root": scan_root,
                "trivy": {
                    "version": trivy_version,
                    "db": trivy_db_info,
                    "options": {
                        "scanners": trivy_scanners.split(","),
                        "severity": trivy_severity,
                        "ignore_unfixed": trivy_ignore_unfixed,
                        "format": "json"
                    }
                }
            },
            "summary": {
                "vulnerabilities_total": sum(trivy_sev_counts.values()),
                "severity_counts": trivy_sev_counts
            }
        }
        
        trivy_metadata_path = os.path.join(scanners_dir, "trivy.metadata.json")
        json.dump(trivy_metadata, open(trivy_metadata_path, "w", encoding="utf-8"), indent=2)
        print("Wrote Trivy outputs:", trivy_latest_json, trivy_metadata_path)
        
        # ============================================================================
        # COMPARISON (CVE-based)
        # ============================================================================
        
        # Extract CVEs from Grype
        grype_cves = set()
        for m in matches:
            cve_id = (m.get("vulnerability", {}) or {}).get("id", "")
            if cve_id and cve_id.startswith("CVE-"):
                grype_cves.add(cve_id)
        
        # Compute set differences
        only_in_grype = sorted(list(grype_cves - trivy_cves))
        only_in_trivy = sorted(list(trivy_cves - grype_cves))
        in_both = sorted(list(grype_cves & trivy_cves))
        
        compare_doc = {
            "schema_version": "1.0",
            "generated_at_utc": now_utc(),
            "target": {
                "product": product,
                "channel": channel,
                "resolved_version": resolved_version
            },
            "summary": {
                "grype": {
                    "cve_count": len(grype_cves),
                    "severity_counts": sev_counts
                },
                "trivy": {
                    "cve_count": len(trivy_cves),
                    "severity_counts": trivy_sev_counts
                }
            },
            "diff": {
                "only_in_grype": only_in_grype,
                "only_in_trivy": only_in_trivy,
                "in_both": in_both
            }
        }
        
        compare_path = os.path.join(scanners_dir, "compare.json")
        json.dump(compare_doc, open(compare_path, "w", encoding="utf-8"), indent=2)
        print("Wrote comparison:", compare_path)
    else:
        print("Trivy scanning disabled (enable_trivy=false)")