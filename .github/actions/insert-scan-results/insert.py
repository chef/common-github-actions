"""
insert.py — Chef Vulnerability Analytics DB insertion script.

Called by the insert-scan-results composite action. Reads the metadata JSON
produced by chef-download-grype-snapshot or automate-container-scan and inserts
summary count rows into the analytics Postgres database.

Only count-level data is stored (no individual CVE IDs). All inserts use
ON CONFLICT DO NOTHING for idempotency — safe to re-run on workflow retries.

DB errors are surfaced as GitHub Actions warnings and do NOT propagate as
exceptions, so a DB outage never blocks the main scan workflow.
"""
from __future__ import annotations

import glob
import json
import os
import sys
import traceback
import warnings
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# GitHub Actions output helpers
# ---------------------------------------------------------------------------

def gha_warning(msg: str) -> None:
    print(f"::warning::{msg}", flush=True)


def gha_notice(msg: str) -> None:
    print(f"::notice::{msg}", flush=True)


def gha_error(msg: str) -> None:
    print(f"::error::{msg}", flush=True)


# ---------------------------------------------------------------------------
# JSON helpers
# ---------------------------------------------------------------------------

def load_json(path: str | Path) -> dict[str, Any] | None:
    p = Path(path)
    if not p.exists():
        return None
    with p.open(encoding="utf-8") as f:
        return json.load(f)


def sev(data: dict, key: str, default: int = 0) -> int:
    """Safe integer extraction from a severity_counts dict."""
    return int(data.get(key, default) or default)


def parse_ts(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp string, returning None on failure."""
    if not value:
        return None
    try:
        # Python 3.11+ handles Z natively; for 3.9/3.10 replace it manually
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# scan_runs upsert
# ---------------------------------------------------------------------------

def upsert_scan_run(cursor, run_id: str, workflow: str, meta: dict) -> None:
    snapshot = meta.get("snapshot", {})
    scan     = meta.get("scan", {})
    grype    = scan.get("grype", {})
    grype_db = grype.get("db", {})

    scanned_at     = parse_ts(snapshot.get("timestamp_utc")) or datetime.now(timezone.utc)
    grype_version  = grype.get("version")
    grype_db_built = parse_ts(grype_db.get("built_utc"))

    cursor.execute(
        """
        INSERT INTO scan_runs (run_id, workflow, scanned_at, grype_version, grype_db_built_at)
        VALUES (%s, %s, %s, %s, %s)
        ON CONFLICT (run_id) DO NOTHING
        """,
        (run_id, workflow, scanned_at, grype_version, grype_db_built),
    )


# ---------------------------------------------------------------------------
# Insertion logic per scan mode
# ---------------------------------------------------------------------------

def insert_native(cursor, run_id: str, workflow: str, env: dict[str, str]) -> None:
    out_dir  = env["OUT_DIR"]
    meta_path = Path(out_dir) / "scanners" / "grype.metadata.json"

    if not meta_path.exists():
        # Fallback: legacy metadata.json at root
        meta_path = Path(out_dir) / "metadata.json"

    meta = load_json(meta_path)
    if meta is None:
        gha_warning(
            f"insert-scan-results: metadata file not found at {meta_path}. "
            "Skipping DB insert for this target."
        )
        return

    upsert_scan_run(cursor, run_id, workflow, meta)

    snapshot = meta.get("snapshot", {})
    target   = meta.get("target", {})
    summary  = meta.get("summary", {})
    sev_c    = summary.get("severity_counts", {})
    size     = target.get("size", {})

    scanned_at       = parse_ts(snapshot.get("timestamp_utc")) or datetime.now(timezone.utc)
    resolved_version = target.get("resolved_version")

    cursor.execute(
        """
        INSERT INTO native_scan_results (
            run_id, scanned_at, scan_mode,
            product, channel, download_site, os, os_version, arch, package_manager,
            resolved_version, skipped,
            matches_total,
            critical_count, high_count, medium_count, low_count, negligible_count, unknown_count,
            package_bytes, installed_bytes
        ) VALUES (
            %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s,
            %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s
        )
        ON CONFLICT ON CONSTRAINT native_scan_results_unique DO NOTHING
        """,
        (
            run_id,
            scanned_at,
            env["SCAN_MODE"],
            env["PRODUCT"],
            env["CHANNEL"],
            env["DOWNLOAD_SITE"],
            env["OS_NAME"],
            env["OS_VERSION"],
            env["ARCH"],
            env["PACKAGE_MANAGER"],
            resolved_version,
            False,  # not skipped — we only call this step when the scan ran
            int(summary.get("matches_total", 0) or 0),
            sev(sev_c, "Critical"),
            sev(sev_c, "High"),
            sev(sev_c, "Medium"),
            sev(sev_c, "Low"),
            sev(sev_c, "Negligible"),
            sev(sev_c, "Unknown"),
            size.get("package_bytes"),
            size.get("installed_bytes"),
        ),
    )

    gha_notice(
        f"insert-scan-results [native/modern]: inserted row for "
        f"{env['PRODUCT']}/{env['CHANNEL']}/{env['DOWNLOAD_SITE']} "
        f"({env['OS_NAME']} {env['OS_VERSION']} {env['ARCH']}) "
        f"version={resolved_version} "
        f"total={summary.get('matches_total', 0)}"
    )


def insert_habitat(cursor, run_id: str, workflow: str, env: dict[str, str]) -> None:
    out_dir   = env["OUT_DIR"]
    hab_ident = env.get("HAB_IDENT", "")

    # The habitat action writes: out/{origin}/{name}/{version}/index.json
    # Glob for all index.json files (one per package version scanned)
    index_files = sorted(glob.glob(str(Path(out_dir) / "*" / "*" / "*" / "index.json")))

    if not index_files:
        gha_warning(
            f"insert-scan-results: no habitat index.json files found under {out_dir}. "
            "Skipping DB insert."
        )
        return

    # Use the first (and typically only) index.json to populate scan_runs
    first_meta = load_json(index_files[0])
    if first_meta:
        # Habitat index.json has a different shape — build a minimal meta dict
        # that upsert_scan_run can consume
        snap_ts = first_meta.get("snapshot", {}).get("timestamp_utc") or \
                  first_meta.get("scanned_at")
        scan_meta = {
            "snapshot": {"timestamp_utc": snap_ts},
            "scan": first_meta.get("scan", {}),
        }
        upsert_scan_run(cursor, run_id, workflow, scan_meta)

    for index_path in index_files:
        data = load_json(index_path)
        if data is None:
            continue

        snapshot         = data.get("snapshot", {})
        target           = data.get("target", {})
        summary          = data.get("summary", {})

        scanned_at       = parse_ts(snapshot.get("timestamp_utc")) or datetime.now(timezone.utc)
        resolved_version = target.get("resolved_version") or target.get("version")
        resolved_release = target.get("resolved_release") or target.get("release")

        # Derive hab_ident from the index.json path if not passed explicitly:
        # out/{origin}/{name}/{version}/index.json → {origin}/{name}
        if not hab_ident:
            parts = Path(index_path).parts
            # parts[-4] = origin, parts[-3] = name
            if len(parts) >= 4:
                hab_ident = f"{parts[-4]}/{parts[-3]}"

        dep_summary   = summary.get("aggregate_severity_counts") or {}
        main_sev      = summary.get("main_severity_counts", {})
        direct_sev    = summary.get("direct_severity_counts", {})
        trans_sev     = summary.get("transitive_severity_counts", {})
        agg_sev       = summary.get("aggregate_severity_counts", {})

        matches_total       = int(summary.get("total_matches", 0) or 0)
        deps_scanned        = int(summary.get("dependencies_scanned", 0) or 0)

        cursor.execute(
            """
            INSERT INTO habitat_scan_results (
                run_id, scanned_at,
                product, channel, hab_ident, resolved_version, resolved_release,
                dependencies_scanned, matches_total,
                main_critical, main_high, main_medium, main_low, main_negligible, main_unknown,
                direct_critical, direct_high, direct_medium, direct_low, direct_negligible, direct_unknown,
                trans_critical, trans_high, trans_medium, trans_low, trans_negligible, trans_unknown,
                agg_critical, agg_high, agg_medium, agg_low, agg_negligible, agg_unknown
            ) VALUES (
                %s, %s,
                %s, %s, %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s
            )
            ON CONFLICT ON CONSTRAINT habitat_scan_results_unique DO NOTHING
            """,
            (
                run_id, scanned_at,
                env["PRODUCT"], env["CHANNEL"], hab_ident, resolved_version, resolved_release,
                deps_scanned, matches_total,
                sev(main_sev, "Critical"), sev(main_sev, "High"), sev(main_sev, "Medium"),
                sev(main_sev, "Low"), sev(main_sev, "Negligible"), sev(main_sev, "Unknown"),
                sev(direct_sev, "Critical"), sev(direct_sev, "High"), sev(direct_sev, "Medium"),
                sev(direct_sev, "Low"), sev(direct_sev, "Negligible"), sev(direct_sev, "Unknown"),
                sev(trans_sev, "Critical"), sev(trans_sev, "High"), sev(trans_sev, "Medium"),
                sev(trans_sev, "Low"), sev(trans_sev, "Negligible"), sev(trans_sev, "Unknown"),
                sev(agg_sev, "Critical"), sev(agg_sev, "High"), sev(agg_sev, "Medium"),
                sev(agg_sev, "Low"), sev(agg_sev, "Negligible"), sev(agg_sev, "Unknown"),
            ),
        )

        gha_notice(
            f"insert-scan-results [habitat]: inserted row for "
            f"{hab_ident}/{env['CHANNEL']} "
            f"version={resolved_version}/{resolved_release} "
            f"total={matches_total} deps={deps_scanned}"
        )


def insert_container(cursor, run_id: str, workflow: str, env: dict[str, str]) -> None:
    out_dir = env["OUT_DIR"]
    channel = env["CHANNEL"]

    # Automate container action writes: out/container/automate/{channel}/ubuntu/25.10/x86_64/index.json
    index_path = Path(out_dir) / "container" / "automate" / channel / "ubuntu" / "25.10" / "x86_64" / "index.json"

    if not index_path.exists():
        # Try a glob fallback in case the OS version changes in the future
        matches = list(Path(out_dir).glob("container/automate/*/ubuntu/*/x86_64/index.json"))
        if matches:
            index_path = matches[0]
        else:
            gha_warning(
                f"insert-scan-results: container index.json not found under {out_dir}. "
                "Skipping DB insert."
            )
            return

    data = load_json(index_path)
    if data is None:
        gha_warning(f"insert-scan-results: failed to parse {index_path}. Skipping.")
        return

    snapshot = data.get("snapshot", {})
    target   = data.get("target", {})
    summary  = data.get("summary", {})

    scan_meta = {"snapshot": snapshot, "scan": data.get("scan", {})}
    upsert_scan_run(cursor, run_id, workflow, scan_meta)

    scanned_at = parse_ts(snapshot.get("timestamp_utc")) or datetime.now(timezone.utc)
    product    = target.get("product", "chef-automate")
    cli_build  = target.get("cli_build")

    for origin_key in ("chef_origin", "core_origin"):
        origin_data = summary.get(origin_key, {})
        if not origin_data:
            continue

        origin_name = origin_key.replace("_origin", "")  # 'chef' | 'core'
        sev_c       = origin_data.get("severity_counts", {})
        size        = origin_data.get("size", {})

        cursor.execute(
            """
            INSERT INTO container_scan_results (
                run_id, scanned_at,
                product, channel, cli_build, origin,
                total_packages, total_vulnerabilities,
                critical_count, high_count, medium_count, low_count, negligible_count,
                total_bytes
            ) VALUES (
                %s, %s,
                %s, %s, %s, %s,
                %s, %s,
                %s, %s, %s, %s, %s,
                %s
            )
            ON CONFLICT ON CONSTRAINT container_scan_results_unique DO NOTHING
            """,
            (
                run_id, scanned_at,
                product, channel, cli_build, origin_name,
                int(origin_data.get("total_packages", 0) or 0),
                int(origin_data.get("total_vulnerabilities", 0) or 0),
                sev(sev_c, "Critical"),
                sev(sev_c, "High"),
                sev(sev_c, "Medium"),
                sev(sev_c, "Low"),
                sev(sev_c, "Negligible"),
                size.get("total_bytes"),
            ),
        )

        gha_notice(
            f"insert-scan-results [container]: inserted row for "
            f"{product}/{channel}/{origin_name} "
            f"cli_build={cli_build} "
            f"total_vulns={origin_data.get('total_vulnerabilities', 0)}"
        )


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    db_url    = os.environ.get("DATABASE_URL", "")
    scan_mode = os.environ.get("SCAN_MODE", "").lower()
    run_id    = os.environ.get("RUN_ID", "")
    workflow  = os.environ.get("WORKFLOW", "unknown")

    env = {
        "SCAN_MODE":       scan_mode,
        "PRODUCT":         os.environ.get("PRODUCT", ""),
        "CHANNEL":         os.environ.get("CHANNEL", ""),
        "DOWNLOAD_SITE":   os.environ.get("DOWNLOAD_SITE", ""),
        "OS_NAME":         os.environ.get("OS_NAME", ""),
        "OS_VERSION":      os.environ.get("OS_VERSION", ""),
        "ARCH":            os.environ.get("ARCH", "x86_64"),
        "PACKAGE_MANAGER": os.environ.get("PACKAGE_MANAGER", ""),
        "HAB_IDENT":       os.environ.get("HAB_IDENT", ""),
        "OUT_DIR":         os.environ.get("OUT_DIR", "out"),
    }

    if not db_url:
        gha_warning(
            "insert-scan-results: DATABASE_URL is empty — skipping DB insert. "
            "Set the SCAN_DB_URL secret to enable analytics tracking."
        )
        return

    if scan_mode not in ("native", "modern", "habitat", "container"):
        gha_warning(
            f"insert-scan-results: unknown scan_mode '{scan_mode}' — skipping DB insert."
        )
        return

    try:
        import psycopg2
    except ImportError:
        gha_warning(
            "insert-scan-results: psycopg2 not available — skipping DB insert."
        )
        return

    conn = None
    try:
        conn = psycopg2.connect(db_url)
        conn.autocommit = False
        with conn.cursor() as cur:
            if scan_mode in ("native", "modern"):
                insert_native(cur, run_id, workflow, env)
            elif scan_mode == "habitat":
                insert_habitat(cur, run_id, workflow, env)
            elif scan_mode == "container":
                insert_container(cur, run_id, workflow, env)
        conn.commit()
        gha_notice("insert-scan-results: DB insert committed successfully.")

    except Exception:  # noqa: BLE001
        # Never block the main scan workflow due to analytics DB issues
        tb = traceback.format_exc()
        gha_warning(
            f"insert-scan-results: DB insert failed (non-fatal). "
            f"Scan results are still written to chef-vuln-scan-data. "
            f"Error: {tb}"
        )
        if conn:
            try:
                conn.rollback()
            except Exception:
                pass
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    main()
