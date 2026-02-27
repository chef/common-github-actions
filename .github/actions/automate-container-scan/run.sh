#!/usr/bin/env bash
# Chef Automate Container Scan Script
# Deploys Automate in a privileged container and scans embedded Habitat packages
set -euo pipefail

# ============================================================================
# Configuration and Environment
# ============================================================================

CHANNEL="${CHANNEL:-current}"
OUT_DIR="${OUT_DIR:-out}"
ACTION_DIR="${ACTION_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"

# Container and Automate state
CONTAINER_ID=""
AUTOMATE_VERSION=""
GRYPE_VERSION=""
GRYPE_DB_BUILT=""
GRYPE_DB_SCHEMA=""

# Output paths
OUT_BASE="${OUT_DIR}/container/automate/${CHANNEL}/ubuntu/25.10/x86_64"
LOGS_DIR="${OUT_DIR}/logs"

# ============================================================================
# Logging and Error Handling
# ============================================================================

log() {
    echo "[$(date +'%Y-%m-%d %H:%M:%S')] $*" >&2
}

fail() {
    log "ERROR: $*"
    cleanup_on_error
    exit 1
}

cleanup_on_error() {
    log "Cleaning up after error..."
    
    if [[ -n "${CONTAINER_ID}" ]]; then
        # Capture container logs for debugging
        log "Capturing container logs to ${LOGS_DIR}/container.log"
        mkdir -p "${LOGS_DIR}"
        docker logs "${CONTAINER_ID}" > "${LOGS_DIR}/container.log" 2>&1 || true
        
        # Stop and remove container
        log "Stopping and removing container ${CONTAINER_ID}"
        docker stop "${CONTAINER_ID}" >/dev/null 2>&1 || true
        docker rm "${CONTAINER_ID}" >/dev/null 2>&1 || true
    fi
}

# Trap errors to ensure cleanup
trap cleanup_on_error ERR

# ============================================================================
# Container Management
# ============================================================================

start_container() {
    log "Starting privileged container with systemd support..."
    
    # Start container with systemd and cgroups (required for Automate)
    CONTAINER_ID=$(docker run -d \
        --privileged \
        --cgroupns=host \
        -v /sys/fs/cgroup:/sys/fs/cgroup:rw \
        automate:latest)
    
    log "Container started: ${CONTAINER_ID:0:12}"
    
    # Wait for systemd to be ready
    log "Waiting for systemd to initialize..."
    sleep 5
    
    # Verify systemd is running
    if ! docker exec "${CONTAINER_ID}" systemctl is-system-running --wait 2>/dev/null; then
        log "WARNING: systemd may not be fully ready, but continuing..."
    fi
}

# ============================================================================
# Chef Automate Deployment
# ============================================================================

deploy_automate() {
    log "Deploying Chef Automate (channel: ${CHANNEL})..."
    mkdir -p "${LOGS_DIR}"
    
    # Initialize Automate configuration
    log "Initializing Automate configuration..."
    if ! docker exec -w /root "${CONTAINER_ID}" chef-automate init-config --upgrade-strategy none \
        > "${LOGS_DIR}/init-config.log" 2>&1; then
        log "ERROR: Failed to initialize Automate config"
        log "Last 20 lines of init-config.log:"
        tail -n 20 "${LOGS_DIR}/init-config.log" || true
        fail "Automate init-config failed"
    fi
    
    # Set required sysctl parameter
    log "Setting sysctl parameters..."
    if ! docker exec -w /root "${CONTAINER_ID}" sysctl -w vm.dirty_expire_centisecs=20000 \
        > "${LOGS_DIR}/sysctl.log" 2>&1; then
        log "ERROR: Failed to set sysctl parameters"
        cat "${LOGS_DIR}/sysctl.log" || true
        fail "sysctl configuration failed"
    fi
    
    # Deploy Automate (this takes 10-15 minutes)
    log "Deploying Automate (this may take 10-15 minutes)..."
    log "Progress will be logged to ${LOGS_DIR}/deploy.log"
    
    # Run deploy with timeout and capture output
    if docker exec -w /root "${CONTAINER_ID}" timeout 1800 chef-automate deploy config.toml --accept-terms-and-mlsa \
        > "${LOGS_DIR}/deploy.log" 2>&1; then
        log "Automate deployment completed successfully"
    else
        log "ERROR: Automate deployment failed or timed out"
        log "Check ${LOGS_DIR}/deploy.log for details"
        fail "Automate deployment failed"
    fi
    
    # Enter maintenance mode
    log "Entering maintenance mode..."
    docker exec -w /root "${CONTAINER_ID}" chef-automate maintenance on \
        > "${LOGS_DIR}/maintenance.log" 2>&1 || log "WARNING: Failed to enter maintenance mode (may not be critical)"
    
    # Capture Automate version (disable pipefail to avoid SIGPIPE from head)
    set +o pipefail
    AUTOMATE_VERSION=$(docker exec -w /root "${CONTAINER_ID}" chef-automate version 2>/dev/null | head -n 1 | awk '{print $NF}')
    set -o pipefail
    log "Chef Automate version: ${AUTOMATE_VERSION}"
    
    # Verify Habitat packages are present
    log "Verifying Habitat packages are installed..."
    if ! docker exec "${CONTAINER_ID}" test -d /hab/pkgs/chef; then
        fail "Habitat packages directory /hab/pkgs/chef not found after deployment"
    fi
    
    if ! docker exec "${CONTAINER_ID}" test -d /hab/pkgs/core; then
        fail "Habitat packages directory /hab/pkgs/core not found after deployment"
    fi
    
    log "Habitat package directories verified"
}

# ============================================================================
# Grype Scanning
# ============================================================================

get_grype_metadata() {
    log "Capturing Grype metadata..."
    
    # Get Grype version (disable pipefail to avoid SIGPIPE from grep/awk)
    set +o pipefail
    GRYPE_VERSION=$(docker exec -w /root "${CONTAINER_ID}" grype version 2>/dev/null | grep "^Version:" | awk '{print $2}')
    set -o pipefail
    log "Grype version: ${GRYPE_VERSION}"
    
    # Get Grype DB metadata
    local db_status
    db_status=$(docker exec -w /root "${CONTAINER_ID}" grype db status 2>/dev/null || echo "")
    
    set +o pipefail
    GRYPE_DB_BUILT=$(echo "${db_status}" | grep "Built:" | awk '{print $2, $3}')
    GRYPE_DB_SCHEMA=$(echo "${db_status}" | grep "Schema version:" | awk '{print $3}')
    set -o pipefail
    
    log "Grype DB built: ${GRYPE_DB_BUILT}"
    log "Grype DB schema: ${GRYPE_DB_SCHEMA}"
}

scan_origin() {
    local origin_name="$1"
    local origin_path="$2"
    local output_file="$3"
    
    log "Scanning ${origin_name} packages at ${origin_path}..."
    
    # Count packages in directory
    local pkg_count
    pkg_count=$(docker exec -w /root "${CONTAINER_ID}" bash -c \
        "find ${origin_path} -mindepth 3 -maxdepth 3 -type d 2>/dev/null | wc -l" || echo "0")
    log "Found ${pkg_count} packages in ${origin_name}"
    
    # Run Grype scan
    log "Running Grype scan (this may take several minutes)..."
    mkdir -p "$(dirname "${output_file}")"
    
    # Run scan and pretty-print JSON output for readability
    if docker exec -w /root "${CONTAINER_ID}" grype "dir:${origin_path}" -o json \
        2>"${LOGS_DIR}/${origin_name}-scan.log" | jq '.' > "${output_file}"; then
        log "Scan completed: ${output_file}"
    else
        log "WARNING: Grype scan of ${origin_name} may have failed"
        log "Check ${LOGS_DIR}/${origin_name}-scan.log for details"
        # Create empty results file to prevent downstream failures
        echo '{"matches":[],"descriptor":{"name":"'"${origin_name}"'","version":""}}' > "${output_file}"
    fi
    
    # Parse severity counts
    local severity_counts
    severity_counts=$(parse_severity_counts "${output_file}")
    
    log "Vulnerabilities in ${origin_name}: ${severity_counts}"
}

parse_severity_counts() {
    local json_file="$1"
    
    # Use Python to parse JSON and extract severity counts
    python3 - <<EOF
import json
import sys

try:
    with open("${json_file}") as f:
        data = json.load(f)
    
    counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0, "Negligible": 0}
    
    for match in data.get("matches", []):
        severity = match.get("vulnerability", {}).get("severity", "Unknown")
        if severity in counts:
            counts[severity] += 1
    
    total = sum(counts.values())
    print(f"{counts['Critical']} critical, {counts['High']} high, {counts['Medium']} medium, {counts['Low']} low, {counts['Negligible']} negligible (total: {total})")
    
except Exception as e:
    print(f"Error parsing JSON: {e}", file=sys.stderr)
    print("0 critical, 0 high, 0 medium, 0 low, 0 negligible (total: 0)")
EOF
}

extract_severity_summary() {
    local json_file="$1"
    
    # Extract severity counts and package info as JSON object
    python3 - <<EOF
import json
import sys

try:
    with open("${json_file}") as f:
        data = json.load(f)
    
    # Count vulnerabilities by severity (same logic as parse_severity_counts)
    counts = {"Critical": 0, "High": 0, "Medium": 0, "Low": 0, "Negligible": 0}
    
    for match in data.get("matches", []):
        severity = match.get("vulnerability", {}).get("severity", "Unknown")
        if severity in counts:
            counts[severity] += 1
    
    # Count unique packages that have vulnerabilities
    artifacts = set()
    for match in data.get("matches", []):
        artifact = match.get("artifact", {})
        name = artifact.get("name", "")
        version = artifact.get("version", "")
        if name and version:
            artifacts.add(f"{name}@{version}")
    
    pkg_count = len(artifacts)
    
    # If no matches, try to get total cataloged packages from source
    if pkg_count == 0 and "source" in data:
        # Some Grype versions include catalog info
        pkg_count = data.get("source", {}).get("target", {}).get("packages", 0)
    
    result = {
        "total_packages": pkg_count,
        "total_vulnerabilities": sum(counts.values()),
        "severity_counts": counts
    }
    
    print(json.dumps(result))
    
except Exception as e:
    # Print error to stderr for debugging
    print(f"Error parsing {json_file}: {e}", file=sys.stderr)
    print(json.dumps({"total_packages": 0, "total_vulnerabilities": 0, "severity_counts": {"Critical": 0, "High": 0, "Medium": 0, "Low": 0, "Negligible": 0}}))
EOF
}

# ============================================================================
# Size Collection
# ============================================================================

get_origin_size() {
    local origin_path="$1"
    
    log "Collecting size information for ${origin_path}..."
    
    # Get total size in bytes and human-readable format
    local size_bytes
    local size_human
    
    # Disable pipefail temporarily for du command
    set +o pipefail
    size_bytes=$(docker exec "${CONTAINER_ID}" bash -c \
        "du -sb ${origin_path} 2>/dev/null | cut -f1" || echo "0")
    size_human=$(docker exec "${CONTAINER_ID}" bash -c \
        "du -sh ${origin_path} 2>/dev/null | cut -f1" || echo "0")
    set -o pipefail
    
    # Count files
    local file_count
    file_count=$(docker exec "${CONTAINER_ID}" bash -c \
        "find ${origin_path} -type f 2>/dev/null | wc -l" || echo "0")
    
    # Return JSON with size info
    jq -n \
        --arg bytes "${size_bytes}" \
        --arg human "${size_human}" \
        --arg files "${file_count}" \
        '{
          "total_bytes": ($bytes | tonumber),
          "total_human": $human,
          "file_count": ($files | tonumber)
        }'
}

# ============================================================================
# Metadata Generation
# ============================================================================

generate_metadata() {
    log "Generating metadata files..."
    
    local index_file="${OUT_BASE}/index.json"
    local timestamp
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    
    # Extract summary for both origins
    local chef_summary
    local core_summary
    chef_summary=$(extract_severity_summary "${OUT_BASE}/chef-origin.json")
    core_summary=$(extract_severity_summary "${OUT_BASE}/core-origin.json")
    
    # Collect size information for both origins
    local chef_size
    local core_size
    chef_size=$(get_origin_size "/hab/pkgs/chef")
    core_size=$(get_origin_size "/hab/pkgs/core")
    
    # Build JSON structure with proper formatting
    # Use jq to merge and format the entire structure properly
    jq -n \
        --arg timestamp "${timestamp}" \
        --arg run_id "${GITHUB_RUN_ID:-local}" \
        --arg repo "${GITHUB_REPOSITORY:-chef/chef-vuln-scan-orchestrator}" \
        --arg git_sha "${GITHUB_SHA:-unknown}" \
        --arg channel "${CHANNEL}" \
        --arg version "${AUTOMATE_VERSION}" \
        --arg grype_version "${GRYPE_VERSION}" \
        --arg grype_db_built "${GRYPE_DB_BUILT}" \
        --arg grype_db_schema "${GRYPE_DB_SCHEMA}" \
        --argjson chef_summary "${chef_summary}" \
        --argjson core_summary "${core_summary}" \
        --argjson chef_size "${chef_size}" \
        --argjson core_size "${core_size}" \
        '{
          "schema_version": "1.0",
          "snapshot": {
            "timestamp_utc": $timestamp,
            "run_id": $run_id,
            "pipeline": {
              "repo": $repo,
              "workflow": "Automate Grype Scan",
              "git_sha": $git_sha
            }
          },
          "target": {
            "product": "chef-automate",
            "channel": $channel,
            "version": $version,
            "scan_type": "container"
          },
          "environment": {
            "runner": "Linux",
            "os": "ubuntu",
            "os_version": "25.10",
            "arch": "x86_64"
          },
          "scan": {
            "mode": "container",
            "origins_scanned": ["chef", "core"],
            "grype": {
              "version": $grype_version,
              "db": {
                "built": $grype_db_built,
                "schema_version": $grype_db_schema
              }
            }
          },
          "summary": {
            "chef_origin": ($chef_summary + {
              "path": "/hab/pkgs/chef",
              "output_file": "chef-origin.json",
              "size": $chef_size
            }),
            "core_origin": ($core_summary + {
              "path": "/hab/pkgs/core",
              "output_file": "core-origin.json",
              "size": $core_size
            })
          }
        }' > "${index_file}"
    
    log "Metadata generated: ${index_file}"
    
    # Display summary (disable pipefail for safe jq parsing)
    set +o pipefail
    log "=== SCAN SUMMARY ==="
    log "Chef Automate version: ${AUTOMATE_VERSION}"
    log "Channel: ${CHANNEL}"
    log "Chef origin: $(echo "${chef_summary}" | jq -r '.total_vulnerabilities') vulnerabilities across $(echo "${chef_summary}" | jq -r '.total_packages') packages"
    log "Core origin: $(echo "${core_summary}" | jq -r '.total_vulnerabilities') vulnerabilities across $(echo "${core_summary}" | jq -r '.total_packages') packages"
    log "==================="
    set -o pipefail
}

# ============================================================================
# Cleanup
# ============================================================================

cleanup() {
    if [[ -n "${CONTAINER_ID}" ]]; then
        log "Stopping and removing container..."
        docker stop "${CONTAINER_ID}" >/dev/null 2>&1 || true
        docker rm "${CONTAINER_ID}" >/dev/null 2>&1 || true
    fi
}

# ============================================================================
# Main Workflow
# ============================================================================

main() {
    log "========================================="
    log "Chef Automate Container Scan"
    log "Channel: ${CHANNEL}"
    log "Output directory: ${OUT_DIR}"
    log "========================================="
    
    # Ensure output directories exist
    mkdir -p "${OUT_BASE}"
    mkdir -p "${LOGS_DIR}"
    
    # Start container
    start_container
    
    # Deploy Automate
    deploy_automate
    
    # Get Grype metadata
    get_grype_metadata
    
    # =========================================================================
    # SCAN HABITAT PACKAGE ORIGINS
    # =========================================================================
    # Chef Automate bundles Habitat packages from multiple origins:
    #
    # 1. "chef" origin (/hab/pkgs/chef/):
    #    - Chef-maintained service packages (e.g., automate-ui, compliance-service)
    #    - These are the core Automate application components
    #
    # 2. "core" origin (/hab/pkgs/core/):
    #    - Binary Bakers maintained packages (foundation layer)
    #    - System dependencies (e.g., gcc, openssl, postgresql, nginx)
    #
    # NOTE: These origins are specific to Chef Automate's Habitat deployment.
    # If Chef Automate changes its origin structure in the future, this list
    # will need to be updated. To discover what origins exist in a deployment:
    #
    #   docker exec <container> ls -1 /hab/pkgs/
    #
    # If additional origins are detected, add new scan_origin calls here and
    # update the "origins_scanned" array in generate_metadata().
    # =========================================================================
    
    scan_origin "chef" "/hab/pkgs/chef" "${OUT_BASE}/chef-origin.json"
    scan_origin "core" "/hab/pkgs/core" "${OUT_BASE}/core-origin.json"
    
    # Generate metadata
    generate_metadata
    
    # Cleanup
    cleanup
    
    log "========================================="
    log "Scan completed successfully!"
    log "Results available in: ${OUT_BASE}"
    log "========================================="
}

# Run main workflow
main "$@"
