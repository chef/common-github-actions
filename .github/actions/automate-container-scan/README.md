# Chef Automate Container Scan Action

A GitHub composite action that deploys Chef Automate in a containerized environment and scans embedded Habitat packages for vulnerabilities using Grype.

## Overview

This action provides automated vulnerability scanning for Chef Automate's embedded Habitat packages. It:

1. Builds a containerized Chef Automate deployment
2. Deploys Automate with systemd support
3. Scans Habitat packages from two origins: `chef` and `core`
4. Generates JSON vulnerability reports compatible with the Chef vulnerability dashboard

## Usage

### Basic Usage

```yaml
- name: Scan Chef Automate
  uses: chef/common-github-actions/.github/actions/automate-container-scan@main
  with:
    channel: current
    out_dir: out
```

### Complete Workflow Example

```yaml
name: Automate Vulnerability Scan
on:
  workflow_dispatch:
  schedule:
    - cron: '0 2 * * *'  # Daily at 2 AM UTC

jobs:
  scan:
    runs-on: ubuntu-latest
    
    steps:
      - name: Checkout common-github-actions
        uses: actions/checkout@v4
        with:
          repository: chef/common-github-actions
          ref: main
          path: common-github-actions
      
      - name: Run Automate container scan
        uses: ./common-github-actions/.github/actions/automate-container-scan
        with:
          channel: current
          out_dir: out
      
      - name: Upload scan results
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: automate-scan-results
          path: |
            out/container/**/*.json
            out/logs/**/*.log
          retention-days: 90
```

## Inputs

| Input | Description | Required | Default |
|-------|-------------|----------|---------|
| `channel` | Release channel for Chef Automate (`stable` or `current`) | No | `current` |
| `out_dir` | Output directory for scan results and logs | No | `out` |

## Outputs

### Directory Structure

```
out/
  container/
    automate/
      current/                    # Channel (current or stable)
        ubuntu/
          25.10/
            x86_64/
              index.json          # Main metadata file
              chef-origin.json    # Grype scan of /hab/pkgs/chef
              core-origin.json    # Grype scan of /hab/pkgs/core
  logs/
    container.log                 # Container logs (on failure)
    deploy.log                    # Automate deployment logs
    chef-scan.log                 # Chef origin scan logs
    core-scan.log                 # Core origin scan logs
```

### Output Files

#### `index.json`
Main metadata file containing:
- Snapshot information (timestamp, run ID, git SHA)
- Target details (product, channel, version)
- Environment details (OS, architecture)
- Scan configuration (Grype version, DB metadata)
- Summary of vulnerabilities by origin and severity

#### `chef-origin.json` and `core-origin.json`
Grype JSON output containing detailed vulnerability information for all packages in each origin.

## Requirements

### Runner Requirements

- **Runner OS**: Linux (Ubuntu 20.04 or later recommended)
- **Docker**: Must support privileged containers with systemd/cgroup mounts
- **Disk Space**: ~10 GB for Automate deployment
- **Memory**: 8 GB minimum recommended
- **Execution Time**: 15-20 minutes for full deployment and scan

### Permissions

The workflow must have permissions to:
- Run privileged Docker containers
- Write to the output directory

## How It Works

### 1. Container Build

Builds a container image based on Ubuntu 25.10 with:
- Chef Automate CLI
- Grype vulnerability scanner
- systemd for service management
- Required dependencies (curl, jq, python3)

### 2. Automate Deployment

Deploys Chef Automate inside the container:
- Starts privileged container with systemd support
- Initializes Automate configuration
- Deploys Automate (10-15 minutes)
- Enters maintenance mode

### 3. Vulnerability Scanning

Scans Habitat packages from two origins:

#### Chef Origin (`/hab/pkgs/chef`)
- **Chef-maintained service packages** that make up the Automate application
- Examples: `automate-ui`, `compliance-service`, `notifications-service`, `event-feed-service`
- These are the core Automate components

#### Core Origin (`/hab/pkgs/core`)
- **Binary Bakers maintained packages** providing the foundation layer
- Examples: `gcc`, `openssl`, `postgresql`, `nginx`, `erlang`
- System dependencies required by Chef packages

Each scan produces a Grype JSON output with:
- Package catalog
- Vulnerability matches
- Severity ratings
- Fix information

**Note on Origin Discovery**: These two origins (`chef` and `core`) are hard-coded based on Chef Automate's current deployment structure. If Chef Automate changes its origin structure in the future, the scan script will need to be updated. To discover what origins exist in a deployment:

```bash
docker exec <container-id> ls -1 /hab/pkgs/
```

If additional origins appear, update the scan calls in `run.sh` and the `origins_scanned` array in the metadata generation function.

### 4. Metadata Generation

Creates `index.json` with:
- Scan metadata and timestamps
- Automate version information
- Vulnerability counts by severity
- Package counts per origin

## Performance and Caching

### Execution Time

Typical run times:
- **Container build**: 1-2 minutes
- **Automate deployment**: 10-15 minutes (cannot be cached)
- **Grype scans**: 3-5 minutes per origin
- **Total**: ~15-20 minutes

### Why We Don't Cache the Deployment

**The Automate deployment cannot be cached** because:
- Even if the Automate version string stays the same, the embedded Habitat packages are updated frequently
- We need to scan the **latest** embedded packages to detect new vulnerabilities
- Caching would miss critical security updates in dependencies

### What Gets Optimized

- **Docker BuildKit**: Enabled for faster image builds with layer caching
- **APT package cache**: Reused within Docker build layers
- **Container reuse**: Same container used for both origin scans

### Recommendations for Scheduled Runs

- Run **nightly** rather than on every commit (deployment time is acceptable for daily scans)
- Use GitHub Actions' schedule trigger during off-peak hours
- Monitor for Automate version changes to detect when fresh scans are needed

## Local Testing

### Build and Test Container

```bash
# Clone the repository
git clone https://github.com/chef/common-github-actions.git
cd common-github-actions/.github/actions/automate-container-scan

# Build the container
docker build -t automate:latest .

# Run the scan script
export CHANNEL=current
export OUT_DIR=out
export ACTION_DIR=$(pwd)
bash run.sh
```

### Interactive Container Access

```bash
# Build container
docker build -t automate:latest .

# Start container with systemd
docker run -d --privileged --cgroupns=host \
  -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
  --name automate-test \
  automate:latest

# Access container
docker exec -it automate-test bash

# Inside container, deploy Automate
chef-automate init-config
sysctl -w vm.dirty_expire_centisecs=20000
chef-automate deploy config.toml --accept-terms-and-mlsa

# Scan packages
cd /hab/pkgs/chef
grype dir:. -o json >> /tmp/chef-origin.json

# Cleanup
docker stop automate-test
docker rm automate-test
```

## Known Limitations

### Current Implementation

- ✅ Internet-based deployment only (requires package downloads)
- ✅ x86_64 architecture only
- ✅ Ubuntu 25.10 base image only
- ✅ Manual trigger or scheduled workflows only

### Not Yet Implemented

- ⏸ Airgap bundle support
- ⏸ Custom Automate configuration
- ⏸ Multi-architecture support (ARM64)
- ⏸ Automatic dashboard integration

### Temporary Solution

This action is a **proof-of-concept** for scanning Chef Automate's embedded packages. It is designed to:
- Be easy to iterate on independently
- Produce outputs compatible with the Chef vulnerability dashboard
- Be removed or replaced when a permanent solution is developed

## Troubleshooting

### Container Fails to Start

**Symptom**: Error about systemd or cgroups

**Solution**: Ensure Docker supports privileged containers and cgroup v2. Check Docker version:
```bash
docker --version  # Recommend 20.10+
```

### Automate Deployment Timeout

**Symptom**: Deployment exceeds 30-minute timeout

**Solution**: 
- Check network connectivity for package downloads
- Increase timeout in `run.sh` (default: 1800 seconds)
- Review `out/logs/deploy.log` for specific errors

### Scan Results Missing

**Symptom**: `chef-origin.json` or `core-origin.json` is empty

**Solution**:
- Check that `/hab/pkgs/chef` and `/hab/pkgs/core` exist after deployment
- Review scan logs in `out/logs/`
- Verify Grype is installed: `docker exec <container> grype version`

### Out of Disk Space

**Symptom**: Deployment fails with disk space errors

**Solution**:
- Ensure at least 10 GB free space on runner
- Clean up Docker images: `docker system prune -a`
- Use larger runner instance

### Detecting New Habitat Origins

**Symptom**: Suspicion that Chef Automate is using new package origins not currently scanned

**Solution**:
1. After deployment, list all origins:
   ```bash
   docker exec <container-id> ls -1 /hab/pkgs/
   ```

2. If origins beyond `chef` and `core` appear, update `run.sh`:
   - Add new `scan_origin` calls in the main() function
   - Update the `origins_scanned` array in `generate_metadata()`
   - Update this README
   
3. Update the dashboard's `container_index.sql` and `container_vulnerabilities.sql` to handle new origins

## Contributing

This action is part of the Chef vulnerability scanning infrastructure. For changes:

1. Test locally using the instructions above
2. Update this README if adding new features
3. Ensure output format remains compatible with dashboard schemas
4. Consider impact on scheduled workflows

## License

Copyright 2025 Chef Software, Inc.

Licensed under the Apache License, Version 2.0.

## Support

- **Documentation**: https://docs.chef.io/automate/
- **Issues**: File in the common-github-actions repository
- **Team**: Chef Security & Engineering teams
