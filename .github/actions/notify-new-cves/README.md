# notify-new-cves Action

Queries the Chef vulnerability analytics database for CVEs first observed within the last 25 hours, enriches each finding with full Grype match details from `chef-vuln-scan-data`, and dispatches notifications to configured channels.

## How It Works

### 1. Detection
Runs a SQL query against `native_cve_details`:
```sql
SELECT * FROM native_cve_details d
LEFT JOIN native_scan_results r ON ...
WHERE d.severity = ANY(severities)
  AND d.first_observed_at >= NOW() - INTERVAL '25 hours'
  AND d.last_seen_at >= NOW() - INTERVAL '25 hours'
```

The dual filter on `first_observed_at` and `last_seen_at` ensures only truly new CVEs are notified (appeared recently AND still present in the latest scan).

The 25-hour window provides resilience for workflows that run slightly late.

### 2. Enrichment
For each CVE found in the database, the script:
- Globs `chef-vuln-scan-data/{scan_mode}/{product}/{channel}/{download_site}/**/scanners/grype.latest.json`
- Finds the match where `vulnerability.id`, `artifact.name`, and `artifact.version` match the DB row
- Extracts the full `vulnerability`, `relatedVulnerabilities`, `matchDetails`, and `artifact` objects
- Reads `metadata.json` from the same directory for scan provenance (timestamp, Grype version, DB version)

### 3. Notification
Each CVE is formatted as a Microsoft Teams Adaptive Card with:
- **Header**: CVE ID, severity, product, version
- **Details**: CVSS score, EPSS percentile, fix state, affected package
- **Description**: Truncated to 500 characters
- **Additional info**: CWEs, install paths, PURL, reference URLs
- **Footer**: Scan timestamp, Grype version, DB version

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `database-url` | Yes | - | PostgreSQL connection string (DSN) |
| `data-repo-path` | Yes | `chef-vuln-scan-data` | Path to checked-out chef-vuln-scan-data repo |
| `severities` | No | `Critical` | Comma-separated severity levels (Critical, High, Medium, Low) |
| `teams-webhook-url` | No | - | Microsoft Teams incoming webhook URL |
| `dry-run` | No | `false` | If `true`, print payloads without sending |

## Usage

### In a workflow
```yaml
- name: Checkout chef-vuln-scan-data
  uses: actions/checkout@v4
  with:
    repository: chef/chef-vuln-scan-data
    token: ${{ secrets.DATA_REPO_TOKEN }}
    path: chef-vuln-scan-data

- name: Notify new CVEs
  uses: ./.github/actions/notify-new-cves
  with:
    database-url: ${{ secrets.DATABASE_URL_RO }}
    data-repo-path: chef-vuln-scan-data
    severities: Critical,High
    teams-webhook-url: ${{ secrets.TEAMS_WEBHOOK_URL }}
    dry-run: false
```

### Dry run for testing
Set `dry-run: true` to print the notification payloads to the Actions log without sending them to Teams. Useful for:
- Verifying query results
- Testing card formatting
- Validating enrichment logic

## Secrets Required

| Secret | Description | Scope |
|--------|-------------|-------|
| `DATABASE_URL_RO` | Postgres connection string (read-only user; only performs SELECT queries) | Org or repo |
| `TEAMS_WEBHOOK_URL` | Teams incoming webhook URL (get from Teams channel connectors) | Org or repo |
| `DATA_REPO_TOKEN` | PAT for checking out chef-vuln-scan-data (already exists) | Org or repo |

## Dispatcher Pattern

The notification logic is architected as a dispatcher so new channels can be added without changing the detection/enrichment logic:

```python
def dispatch_notifications(notifications, teams_webhook=None, email_config=None, jira_config=None):
    if teams_webhook:
        send_teams_notification(notifications, teams_webhook)
    if email_config:
        send_email_notification(notifications, email_config)  # Future
    if jira_config:
        create_jira_issues(notifications, jira_config)        # Future
```

To add a new channel, implement a new `send_*` function and add it to the dispatcher.

## Scheduled Workflow

The workflow that calls this action lives in [chef/chef-vuln-scan-orchestrator](https://github.com/chef/chef-vuln-scan-orchestrator):
- Path: `.github/workflows/notify-new-cves.yml`
- Schedule: 10:00 UTC daily (after nightly scans complete around 07:00 UTC)
- Advantage: Uses existing `DATA_REPO_TOKEN` secret already configured in the orchestrator

## Verification Steps

### 1. Dry run
Trigger `cd-notify-new-cves.yml` manually with `dry-run: true` — confirm formatted card payload appears in the Actions log.

### 2. Inject test row
Manually insert a test CVE into `native_cve_details`:
```sql
INSERT INTO native_cve_details (
    scan_mode, product, channel, download_site,
    cve_id, severity, package_name, package_version,
    fix_available, fix_version,
    first_observed_at, last_seen_at
) VALUES (
    'native', 'test-product', 'stable', 'commercial',
    'CVE-2025-99999', 'Critical', 'test-package', '1.0.0',
    false, NULL,
    NOW(), NOW()
);
```

Trigger dry run and confirm the test CVE is detected and enriched.

### 3. End-to-end
Remove `dry-run: true` and trigger the workflow — confirm a Teams message arrives in the configured channel.

### 4. No false positives
Re-run the workflow the next day when no new CVEs exist — confirm no messages are sent.

## Limitations

- **Scope**: Only native/modern products (habitat and container scans not yet supported)
- **Deduplication**: A CVE appearing in multiple OS/arch platforms will send multiple notifications (one per unique product × CVE × package combination)
- **Rate limiting**: Teams webhooks have rate limits (check Microsoft docs); may need throttling for large batches
