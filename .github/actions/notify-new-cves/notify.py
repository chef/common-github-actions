"""
notify.py — Chef Vulnerability Analytics CVE Notification Script

Queries the analytics database for CVEs with first_observed_at within the last
25 hours, enriches each finding with the full Grype match object from the
chef-vuln-scan-data repository, and dispatches notifications to configured
channels (Teams, email, Jira, etc.).

The 25-hour window (not 24h) provides resilience for workflows that run slightly
late.

Usage:
    python notify.py --database-url <dsn> --data-repo <path> [options]

Required inputs:
    --database-url: Postgres connection string
    --data-repo: Path to checked-out chef-vuln-scan-data repository

Optional inputs:
    --severities: Comma-separated list (default: Critical)
    --teams-webhook: Teams incoming webhook URL
    --dry-run: Print notification payload without sending
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import traceback
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# GitHub Actions output helpers
# ---------------------------------------------------------------------------

def gha_warning(msg: str) -> None:
    """Print a GitHub Actions warning annotation."""
    print(f"::warning::{msg}", flush=True)


def gha_notice(msg: str) -> None:
    """Print a GitHub Actions notice annotation."""
    print(f"::notice::{msg}", flush=True)


def gha_error(msg: str) -> None:
    """Print a GitHub Actions error annotation."""
    print(f"::error::{msg}", flush=True)


# ---------------------------------------------------------------------------
# Notification data model
# ---------------------------------------------------------------------------

@dataclass
class Notification:
    """
    Complete notification payload for a single CVE finding.
    Combines DB row + Grype match object + metadata.json provenance.
    """
    # From database
    cve_id: str
    severity: str
    product: str
    channel: str
    download_site: str
    scan_mode: str
    package_name: str
    package_version: str
    fix_available: bool
    fix_version: str | None
    first_observed_at: datetime
    last_seen_at: datetime
    
    # From scan metadata
    resolved_version: str | None = None
    os: str | None = None
    os_version: str | None = None
    arch: str | None = None
    scan_timestamp: datetime | None = None
    grype_version: str | None = None
    grype_db_version: str | None = None
    grype_db_built: datetime | None = None
    
    # From Grype match object
    vulnerability: dict = field(default_factory=dict)
    related_vulnerabilities: list[dict] = field(default_factory=list)
    match_details: dict = field(default_factory=dict)
    artifact: dict = field(default_factory=dict)
    
    def get_canonical_cve(self) -> str:
        """
        Return the canonical CVE ID. If the primary ID is a GHSA, check
        relatedVulnerabilities for a CVE alias and prefer that for display.
        """
        if self.cve_id.startswith("CVE-"):
            return self.cve_id
        
        # Check related vulnerabilities for CVE alias
        for related in self.related_vulnerabilities:
            rel_id = related.get("id", "")
            if rel_id.startswith("CVE-"):
                return rel_id
        
        return self.cve_id
    
    def get_cvss_score(self) -> float | None:
        """Extract CVSS base score from vulnerability data."""
        cvss_list = self.vulnerability.get("cvss", [])
        if cvss_list and isinstance(cvss_list, list):
            for cvss in cvss_list:
                metrics = cvss.get("metrics", {})
                base_score = metrics.get("baseScore")
                if base_score is not None:
                    return float(base_score)
        return None
    
    def get_epss_percentile(self) -> float | None:
        """Extract EPSS percentile from vulnerability data."""
        epss = self.vulnerability.get("epss")
        if epss and isinstance(epss, dict):
            percentile = epss.get("percentile")
            if percentile is not None:
                return float(percentile)
        return None
    
    def get_description(self) -> str:
        """Get vulnerability description."""
        return self.vulnerability.get("description", "No description available")
    
    def get_cwes(self) -> list[str]:
        """Get list of CWE IDs."""
        cwes = self.vulnerability.get("cwes", [])
        if isinstance(cwes, list):
            return [cwe for cwe in cwes if cwe]
        return []
    
    def get_urls(self) -> list[str]:
        """Get reference URLs."""
        urls = self.vulnerability.get("urls", [])
        if isinstance(urls, list):
            return [url for url in urls if url]
        return []
    
    def get_install_paths(self) -> list[str]:
        """Get artifact installation paths."""
        locations = self.artifact.get("locations", [])
        if isinstance(locations, list):
            paths = []
            for loc in locations:
                if isinstance(loc, dict):
                    path = loc.get("path", "")
                    if path:
                        paths.append(path)
            return paths
        return []
    
    def get_purl(self) -> str:
        """Get package URL."""
        return self.artifact.get("purl", "")


# ---------------------------------------------------------------------------
# Database query
# ---------------------------------------------------------------------------

def query_new_cves(cursor, severities: list[str]) -> list[dict]:
    """
    Query the database for CVEs first observed within the last 25 hours
    that are still present in the most recent scan.
    
    Returns a list of dict rows with columns from native_cve_details joined
    with native_scan_results for the latest run.
    """
    query = """
    WITH latest_run AS (
        SELECT run_id, scanned_at
        FROM scan_runs
        ORDER BY scanned_at DESC
        LIMIT 1
    )
    SELECT 
        d.cve_id,
        d.severity,
        d.product,
        d.channel,
        d.download_site,
        d.scan_mode,
        d.package_name,
        d.package_version,
        d.fix_available,
        d.fix_version,
        d.first_observed_at,
        d.last_seen_at,
        r.resolved_version,
        r.os,
        r.os_version,
        r.arch
    FROM native_cve_details d
    LEFT JOIN native_scan_results r
        ON r.product = d.product 
        AND r.channel = d.channel
        AND r.download_site = d.download_site 
        AND r.scan_mode = d.scan_mode
        AND r.run_id = (SELECT run_id FROM latest_run)
    WHERE d.severity = ANY(%(severities)s)
        AND d.first_observed_at >= NOW() - INTERVAL '25 hours'
        AND d.last_seen_at >= NOW() - INTERVAL '25 hours'
    ORDER BY d.first_observed_at DESC, d.severity DESC
    """
    
    cursor.execute(query, {"severities": severities})
    
    columns = [desc[0] for desc in cursor.description]
    rows = []
    for row in cursor.fetchall():
        rows.append(dict(zip(columns, row)))
    
    return rows


# ---------------------------------------------------------------------------
# Enrichment from Grype JSON
# ---------------------------------------------------------------------------

def find_grype_match(
    data_repo: Path,
    scan_mode: str,
    product: str,
    channel: str,
    download_site: str,
    cve_id: str,
    package_name: str,
    package_version: str,
) -> tuple[dict | None, dict | None]:
    """
    Find the Grype match object for the given CVE + package combination.
    
    Returns (match_object, metadata) or (None, None) if not found.
    
    Globs: chef-vuln-scan-data/{scan_mode}/{product}/{channel}/{download_site}/**/scanners/grype.latest.json
    """
    pattern = str(
        data_repo / scan_mode / product / channel / download_site / "**/scanners/grype.latest.json"
    )
    
    grype_files = glob.glob(pattern, recursive=True)
    
    for grype_path in grype_files:
        try:
            with open(grype_path, encoding="utf-8") as f:
                grype_data = json.load(f)
            
            matches = grype_data.get("matches", [])
            for match in matches:
                vuln = match.get("vulnerability", {})
                artifact = match.get("artifact", {})
                
                if (
                    vuln.get("id") == cve_id
                    and artifact.get("name") == package_name
                    and artifact.get("version") == package_version
                ):
                    # Also read metadata.json from the same directory
                    grype_dir = Path(grype_path).parent
                    metadata_path = grype_dir.parent / "metadata.json"
                    metadata = None
                    if metadata_path.exists():
                        with open(metadata_path, encoding="utf-8") as mf:
                            metadata = json.load(mf)
                    
                    return match, metadata
        
        except (OSError, json.JSONDecodeError) as e:
            gha_warning(f"Failed to read {grype_path}: {e}")
            continue
    
    return None, None


def enrich_notification(db_row: dict, data_repo: Path) -> Notification:
    """
    Create a Notification object from a DB row, enriched with Grype match
    details and metadata.
    """
    match, metadata = find_grype_match(
        data_repo,
        db_row["scan_mode"],
        db_row["product"],
        db_row["channel"],
        db_row["download_site"],
        db_row["cve_id"],
        db_row["package_name"],
        db_row["package_version"],
    )
    
    notification = Notification(
        cve_id=db_row["cve_id"],
        severity=db_row["severity"],
        product=db_row["product"],
        channel=db_row["channel"],
        download_site=db_row["download_site"],
        scan_mode=db_row["scan_mode"],
        package_name=db_row["package_name"],
        package_version=db_row["package_version"],
        fix_available=db_row["fix_available"],
        fix_version=db_row["fix_version"],
        first_observed_at=db_row["first_observed_at"],
        last_seen_at=db_row["last_seen_at"],
        resolved_version=db_row.get("resolved_version"),
        os=db_row.get("os"),
        os_version=db_row.get("os_version"),
        arch=db_row.get("arch"),
    )
    
    if match:
        notification.vulnerability = match.get("vulnerability", {})
        notification.related_vulnerabilities = match.get("relatedVulnerabilities", [])
        notification.match_details = match.get("matchDetails", [])
        notification.artifact = match.get("artifact", {})
    
    if metadata:
        snapshot = metadata.get("snapshot", {})
        scan = metadata.get("scan", {})
        grype = scan.get("grype", {})
        grype_db = grype.get("db", {})
        
        notification.scan_timestamp = parse_timestamp(snapshot.get("timestamp_utc"))
        notification.grype_version = grype.get("version")
        notification.grype_db_version = grype_db.get("version")
        notification.grype_db_built = parse_timestamp(grype_db.get("built_utc"))
    
    return notification


def parse_timestamp(value: str | None) -> datetime | None:
    """Parse an ISO-8601 timestamp string."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


# ---------------------------------------------------------------------------
# Teams notification formatter
# ---------------------------------------------------------------------------

def format_teams_card(notification: Notification) -> dict:
    """
    Format a notification as a Microsoft Teams Adaptive Card.
    
    See: https://adaptivecards.io/
    """
    canonical_cve = notification.get_canonical_cve()
    cvss_score = notification.get_cvss_score()
    epss_percentile = notification.get_epss_percentile()
    description = notification.get_description()
    cwes = notification.get_cwes()
    urls = notification.get_urls()
    install_paths = notification.get_install_paths()
    purl = notification.get_purl()
    
    # Severity color mapping
    color_map = {
        "Critical": "Attention",  # Red
        "High": "Warning",        # Orange
        "Medium": "Good",         # Green (shouldn't happen but safe default)
        "Low": "Good",
    }
    color = color_map.get(notification.severity, "Default")
    
    # Build header
    header_text = f"🚨 New {notification.severity} CVE: {canonical_cve}"
    if notification.resolved_version:
        header_text += f" in {notification.product} {notification.resolved_version}"
    else:
        header_text += f" in {notification.product}"
    
    # Build facts table
    facts = [
        {"title": "Severity", "value": notification.severity},
        {"title": "Product", "value": notification.product},
        {"title": "Version", "value": notification.resolved_version or "Unknown"},
        {"title": "Channel", "value": notification.channel},
        {"title": "Download Site", "value": notification.download_site},
        {"title": "Package", "value": f"{notification.package_name} {notification.package_version}"},
    ]
    
    if cvss_score is not None:
        facts.append({"title": "CVSS Score", "value": f"{cvss_score:.1f}"})
    
    if epss_percentile is not None:
        facts.append({"title": "EPSS Percentile", "value": f"{epss_percentile:.1%}"})
    
    if notification.fix_available:
        fix_text = notification.fix_version or "Available (version unknown)"
        facts.append({"title": "Fix", "value": fix_text})
    else:
        facts.append({"title": "Fix", "value": "Not available"})
    
    # Build card body
    card_body = [
        {
            "type": "TextBlock",
            "text": header_text,
            "size": "Large",
            "weight": "Bolder",
            "wrap": True,
        },
        {
            "type": "FactSet",
            "facts": facts,
        },
    ]
    
    # Add description
    if description:
        card_body.append({
            "type": "TextBlock",
            "text": "**Description:**",
            "weight": "Bolder",
            "spacing": "Medium",
        })
        card_body.append({
            "type": "TextBlock",
            "text": description[:500] + ("..." if len(description) > 500 else ""),
            "wrap": True,
            "spacing": "Small",
        })
    
    # Add CWEs
    if cwes:
        card_body.append({
            "type": "TextBlock",
            "text": f"**CWEs:** {', '.join(cwes)}",
            "wrap": True,
            "spacing": "Medium",
        })
    
    # Add install paths
    if install_paths:
        paths_text = ", ".join(install_paths[:3])
        if len(install_paths) > 3:
            paths_text += f" (and {len(install_paths) - 3} more)"
        card_body.append({
            "type": "TextBlock",
            "text": f"**Installed at:** {paths_text}",
            "wrap": True,
            "spacing": "Small",
        })
    
    # Add PURL
    if purl:
        card_body.append({
            "type": "TextBlock",
            "text": f"**PURL:** `{purl}`",
            "wrap": True,
            "spacing": "Small",
        })
    
    # Add reference links
    if urls:
        card_body.append({
            "type": "TextBlock",
            "text": "**References:**",
            "weight": "Bolder",
            "spacing": "Medium",
        })
        for url in urls[:5]:  # Limit to 5 to avoid card bloat
            card_body.append({
                "type": "TextBlock",
                "text": f"[{url}]({url})",
                "wrap": True,
                "spacing": "Small",
            })
    
    # Add footer with scan metadata
    footer_parts = []
    if notification.scan_timestamp:
        footer_parts.append(f"Scanned: {notification.scan_timestamp.strftime('%Y-%m-%d %H:%M UTC')}")
    if notification.grype_version:
        footer_parts.append(f"Grype {notification.grype_version}")
    if notification.grype_db_version:
        footer_parts.append(f"DB {notification.grype_db_version}")
    
    if footer_parts:
        card_body.append({
            "type": "TextBlock",
            "text": " | ".join(footer_parts),
            "size": "Small",
            "isSubtle": True,
            "spacing": "Medium",
        })
    
    # Build the complete Adaptive Card
    card = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "type": "AdaptiveCard",
                    "body": card_body,
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "version": "1.4",
                },
            }
        ],
    }
    
    return card


def send_teams_notification(notifications: list[Notification], webhook_url: str, dry_run: bool = False) -> None:
    """
    Send notifications to Microsoft Teams via incoming webhook.
    
    If dry_run is True, print the payload without sending.
    """
    if not notifications:
        gha_notice("No new CVEs to notify")
        return
    
    for notification in notifications:
        card = format_teams_card(notification)
        
        if dry_run:
            gha_notice(f"[DRY RUN] Would send Teams notification for {notification.cve_id}")
            print(json.dumps(card, indent=2))
        else:
            try:
                import urllib.request
                
                req = urllib.request.Request(
                    webhook_url,
                    data=json.dumps(card).encode("utf-8"),
                    headers={"Content-Type": "application/json"},
                )
                
                with urllib.request.urlopen(req, timeout=10) as response:
                    if response.status == 200:
                        gha_notice(f"Sent Teams notification for {notification.cve_id}")
                    else:
                        gha_warning(
                            f"Teams webhook returned status {response.status} for {notification.cve_id}"
                        )
            
            except Exception as e:
                gha_error(f"Failed to send Teams notification for {notification.cve_id}: {e}")


# ---------------------------------------------------------------------------
# Notification dispatcher
# ---------------------------------------------------------------------------

def dispatch_notifications(
    notifications: list[Notification],
    teams_webhook: str | None = None,
    dry_run: bool = False,
) -> None:
    """
    Dispatch notifications to all configured channels.
    
    This dispatcher pattern allows adding new channels (email, Jira, etc.)
    without changing the detection/enrichment logic.
    """
    if not notifications:
        gha_notice("No new CVEs detected — no notifications to send")
        return
    
    gha_notice(f"Found {len(notifications)} new CVE(s) to notify")
    
    # Teams channel
    if teams_webhook:
        send_teams_notification(notifications, teams_webhook, dry_run)
    
    # Future channels:
    # if email_config:
    #     send_email_notification(notifications, email_config, dry_run)
    # if jira_config:
    #     create_jira_issues(notifications, jira_config, dry_run)


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Query DB for new CVEs and send notifications"
    )
    parser.add_argument(
        "--database-url",
        required=True,
        help="PostgreSQL connection string",
    )
    parser.add_argument(
        "--data-repo",
        required=True,
        help="Path to chef-vuln-scan-data repository",
    )
    parser.add_argument(
        "--severities",
        default="Critical",
        help="Comma-separated severity levels to notify (default: Critical)",
    )
    parser.add_argument(
        "--teams-webhook",
        help="Microsoft Teams incoming webhook URL",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print notifications without sending",
    )
    
    args = parser.parse_args()
    
    # Parse severities
    severities = [s.strip() for s in args.severities.split(",")]
    
    # Validate data repo path
    data_repo = Path(args.data_repo)
    if not data_repo.exists():
        gha_error(f"Data repo path does not exist: {data_repo}")
        return 1
    
    # Connect to database
    try:
        import psycopg2
        import psycopg2.extras
    except ImportError:
        gha_error("psycopg2 not installed — run: pip install psycopg2-binary")
        return 1
    
    try:
        conn = psycopg2.connect(args.database_url)
        cursor = conn.cursor()
        
        # Query for new CVEs
        gha_notice(f"Querying for new CVEs with severity: {', '.join(severities)}")
        db_rows = query_new_cves(cursor, severities)
        gha_notice(f"Found {len(db_rows)} new CVE(s) in database")
        
        # Enrich each row with Grype match details
        notifications = []
        for row in db_rows:
            notification = enrich_notification(row, data_repo)
            notifications.append(notification)
            
            if not notification.vulnerability:
                gha_warning(
                    f"Could not find Grype match for {row['cve_id']} / "
                    f"{row['package_name']} {row['package_version']} — "
                    "notification will have limited details"
                )
        
        # Dispatch notifications
        dispatch_notifications(
            notifications,
            teams_webhook=args.teams_webhook,
            dry_run=args.dry_run,
        )
        
        cursor.close()
        conn.close()
        
        return 0
    
    except Exception as e:
        gha_error(f"Notification failed: {e}")
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
