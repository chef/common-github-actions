# CVE Notifier Setup Guide

## Quick Start

The CVE notification system has been implemented in three components:

1. **notify.py** - Python script that queries the database, enriches with Grype data, and sends Teams notifications
2. **action.yml** - GitHub Action wrapper around notify.py
3. **cd-notify-new-cves.yml** - Scheduled workflow that runs daily at 10:00 UTC (in another repo).

## Files Created

```
common-github-actions/
├── .github/
│   ├── actions/
│   │   └── notify-new-cves/
│   │       ├── action.yml         # Action definition
│   │       ├── notify.py          # Core notification script
│   │       └── README.md          # Detailed documentation
│   └── workflows/
│       └── cd-notify-new-cves.yml # Daily scheduled workflow
```

## Prerequisites

### 1. Create GitHub Secrets

Add these secrets to the `chef/chef-vuln-scan-orchestrator` repository (or at org level):

| Secret Name | Description | How to Get It |
|------------|-------------|---------------|
| `DATABASE_URL_RO` | Postgres connection string (read-only user) | From your RDS instance or infrastructure team |
| `TEAMS_WEBHOOK_URL` | Teams incoming webhook URL | Create in Teams: Channel → Connectors → Incoming Webhook |
| `DATA_REPO_TOKEN` | PAT for chef-vuln-scan-data | Should already exist (used by scan workflows) |

**Note**: The notification workflow only performs `SELECT` queries on `scan_runs`, `native_cve_details`, and `native_scan_results`. No write operations are performed—you can use a dedicated read-only database user for security.

#### Database URL Format

PostgreSQL connection string format:
- Scheme: `postgresql`
- Format: `<scheme>://<username>:<password>@<hostname>:<port>/<database>`
- Default port: `5432`

Replace the angle-bracketed placeholders with your actual connection details.

#### Teams Webhook URL
1. In Microsoft Teams, go to the channel where you want notifications
2. Click the `...` menu → Connectors → Incoming Webhook
3. Name: "Chef CVE Alerts" (or similar)
4. Upload an icon (optional)
5. Click "Create"
6. Copy the webhook URL (starts with `https://progress.webhook.office.com/...`)
7. Add as GitHub secret

### 2. Verify Database Schema

Ensure your database has the latest migrations applied:
```bash
cd chef-vuln-scan-db
./scripts/migrate.sh
```

Required tables:
- `scan_runs` (stores run metadata)
- `native_cve_details` (stores individual CVE findings)
- `native_scan_results` (stores scan result aggregates)

### 3. Verify Data Repository Access

The workflow checks out `chef/chef-vuln-scan-data` using `DATA_REPO_TOKEN`. Verify this secret has read access.

## Testing

### Dry Run (Recommended First Step)

1. Go to the [chef-vuln-scan-orchestrator](https://github.com/chef/chef-vuln-scan-orchestrator) repo
2. Navigate to Actions → Notify New CVEs
3. Click "Run workflow"
4. Set `dry-run` to `true`
5. Set `severities` to `Critical` (or `Critical,High` for testing)
6. Click "Run workflow"

This will:
- Query the database
- Enrich findings with Grype data
- Print the Teams card payload to the Actions log
- **NOT** send any actual notifications

Review the output to ensure:
- CVEs are being detected correctly
- Enrichment finds the Grype match data
- Card formatting looks good

### Test with Injected CVE

If you want to test without waiting for a real CVE, inject a test row:

```sql
-- Connect to your database
psql $DATABASE_URL

-- Insert a test CVE
INSERT INTO native_cve_details (
    scan_mode, product, channel, download_site,
    cve_id, severity, package_name, package_version,
    fix_available, fix_version,
    first_observed_at, last_seen_at
) VALUES (
    'native', 'chef', 'stable', 'commercial',
    'CVE-2025-TEST', 'Critical', 'test-package', '1.0.0',
    false, NULL,
    NOW(), NOW()
) ON CONFLICT DO NOTHING;

-- Verify it was inserted
SELECT * FROM native_cve_details WHERE cve_id = 'CVE-2025-TEST';
```

Then run a dry-run workflow. You should see the test CVE in the output.

**Important**: Clean up the test row after testing:
```sql
DELETE FROM native_cve_details WHERE cve_id = 'CVE-2025-TEST';
```

### Live Test

Once dry-run looks good:

1. Run workflow again with `dry-run` set to `false`
2. Check your Teams channel for the notification
3. Verify the card displays correctly
4. Click through the reference links to ensure they work

### Verify No False Positives

Run the workflow again immediately (or the next day when no new CVEs exist). It should:
- Find 0 new CVEs
- Print: "No new CVEs detected — no notifications to send"
- **NOT** send any Teams messages

## Production Schedule

The workflow (located in `chef-vuln-scan-orchestrator/.github/workflows/notify-new-cves.yml`) can be enabled to run automatically daily at **10:00 UTC** by uncommenting the schedule:

```yaml
schedule:
  - cron: '0 10 * * *'
```

This is 3 hours after the nightly scans complete (~07:00 UTC), providing buffer time.

The schedule is commented out by default to allow testing with manual runs first.

## Customization

### Change Severity Threshold

Edit the workflow file to notify on High severity as well:
```yaml
severities: Critical,High
```

Or run manually with custom severities via workflow_dispatch.

### Add Email Notifications

The dispatcher pattern makes this easy:

1. Add email configuration as a secret (JSON with SMTP settings)
2. Implement `send_email_notification()` in notify.py
3. Add email logic to `dispatch_notifications()`
4. Add input to action.yml and workflow

### Add Jira Integration

Similar pattern:

1. Add Jira credentials as secrets
2. Implement `create_jira_issues()` in notify.py
3. Add to dispatcher
4. Configure in action.yml/workflow

## Monitoring

### Check Workflow Runs

- Go to [chef-vuln-scan-orchestrator Actions](https://github.com/chef/chef-vuln-scan-orchestrator/actions)
- Select "Notify New CVEs" workflow
- Review recent runs for failures
- Check logs for warnings about missing Grype matches

### Common Issues

**No CVEs found but expecting some:**
- Check database: `SELECT * FROM native_cve_details WHERE first_observed_at >= NOW() - INTERVAL '25 hours'`
- Verify scan workflows are running and inserting data
- Check `last_seen_at` values are recent

**Grype match not found:**
- Verify chef-vuln-scan-data repo has the grype.latest.json files
- Check the file path pattern matches: `{scan_mode}/{product}/{channel}/{download_site}/**/scanners/grype.latest.json`
- Look for warning in Actions log: "Could not find Grype match for..."

**Teams notification not arriving:**
- Verify webhook URL is correct
- Check Teams webhook hasn't been deleted/disabled
- Look for HTTP error in Actions log
- Test webhook manually with curl

**Database connection fails:**
- Verify DATABASE_URL_RO secret is correct
- Check database is accessible from GitHub Actions runners (security groups/firewalls)
- Ensure the read-only user has SELECT permissions on the required tables

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  GitHub Actions: cd-notify-new-cves.yml                     │
│  Schedule: Daily at 10:00 UTC                               │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│  Action: notify-new-cves                                     │
│  ┌─────────────────────────────────────────────────────┐   │
│  │  notify.py                                           │   │
│  │  1. Query Postgres for new CVEs (first_observed_at) │   │
│  │  2. Enrich with Grype match from chef-vuln-scan-data│   │
│  │  3. Format as Teams Adaptive Card                    │   │
│  │  4. Send to webhook (or dry-run)                     │   │
│  └─────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────┘
                           │
                           ▼
                   ┌──────────────┐
                   │ Microsoft    │
                   │ Teams        │
                   │ Channel      │
                   └──────────────┘
```

## Next Steps

1. ✅ Create GitHub secrets (DATABASE_URL_RO, TEAMS_WEBHOOK_URL)
2. ✅ Run dry-run test
3. ✅ Inject test CVE and verify detection
4. ✅ Run live test (send one notification to Teams)
5. ✅ Monitor first scheduled run at 10:00 UTC tomorrow
6. ⏳ Consider adding High severity notifications
7. ⏳ Extend to Habitat scans (requires habitat_cve_details query)
8. ⏳ Add email/Jira channels as needed
