# Chef Download + Grype + Trivy Snapshot Action

Composite action that downloads Chef products and runs both Grype and Trivy vulnerability scans for comprehensive vulnerability detection.

Supports three scan modes:
- **native**: Downloads packages from Chef download sites and scans them (supports both Grype and Trivy)
- **modern**: Downloads next-generation products (chef-ice) with flexible channel configurations
- **habitat**: Installs Habitat packages and scans each dependency separately (Grype only)

## Usage

### Native Mode - Standard Products

```yaml
- name: Scan chef product (native)
  uses: chef/common-github-actions/.github/actions/chef-download-grype-snapshot@main
  with:
    product: chef
    channel: stable
    download_site: commercial
    os: ubuntu
    os_version: "24.04"
    arch: x86_64
    scan_mode: native
    scan_root: /opt/chef
    license_id: ${{ secrets.LICENSE_ID }}
    enable_trivy: true
    trivy_scanners: vuln
```

### Native Mode - CINC (Open Source)

```yaml
- name: Scan CINC (open source Chef)
  uses: chef/common-github-actions/.github/actions/chef-download-grype-snapshot@main
  with:
    product: chef  # Mapped internally to 'cinc'
    channel: stable
    download_site: cinc
    os: ubuntu
    os_version: "24.04"
    arch: x86_64
    scan_mode: native
    scan_root: /opt/cinc
    enable_trivy: true
```

### Modern Mode - Next-Gen Products (chef-ice)

```yaml
- name: Scan chef-ice (modern product)
  uses: chef/common-github-actions/.github/actions/chef-download-grype-snapshot@main
  with:
    product: chef-ice
    channel: stable
    download_site: commercial
    os: linux
    os_version: ""  # Not needed for universal binaries
    arch: x86_64
    package_manager: deb  # Required: deb, rpm, or tar
    scan_mode: modern
    scan_root: /hab
    license_id: ${{ secrets.LICENSE_ID }}
    enable_trivy: true
```

### Modern Mode - With Base URL Override (current channel)

```yaml
- name: Scan chef-ice current channel
  uses: chef/common-github-actions/.github/actions/chef-download-grype-snapshot@main
  with:
    product: chef-ice
    channel: current
    download_site: commercial
    os: linux
    arch: x86_64
    package_manager: deb
    scan_mode: modern
    scan_root: /hab
    license_id: ${{ secrets.CHEF_ACCEPTANCE_LICENSE_ID }}
    base_url_override: https://commercial-acceptance.downloads.chef.co
    enable_trivy: true
```

### Habitat Mode

```yaml
- name: Scan chef habitat package
  uses: chef/common-github-actions/.github/actions/chef-download-grype-snapshot@main
  with:
    product: chef-infra-client
    channel: stable
    os: ubuntu
    os_version: "24.04"
    arch: x86_64
    scan_mode: habitat
    hab_ident: "chef/chef-infra-client"
    hab_channel: stable
    hab_auth_token: ${{ secrets.HAB_AUTH_TOKEN }}
```

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `product` | Yes | - | Chef product name (chef, chef-workstation, chef-server, inspec, chef-ice, etc.) |
| `channel` | Yes | - | Release channel (stable, current) or target channel for native/modern/habitat |
| `download_site` | Yes | commercial | Download site (commercial, community, or cinc) - native/modern modes only |
| `os` | Yes | ubuntu | OS platform (ubuntu for standard products, linux for universal binaries) |
| `os_version` | No | "" | OS version (e.g., 24.04) - optional for universal binaries like chef-ice |
| `arch` | Yes | x86_64 | Architecture |
| `package_manager` | No | "" | Package manager type (deb, rpm, tar) - required for universal binaries like chef-ice |
| `scan_mode` | Yes | native | Scan mode (native, modern, or habitat) |
| `scan_root` | Yes | - | Install root path for metadata (e.g., /opt/chef) - native/modern modes only |
| `resolve_version` | Yes | latest | Version resolution (latest or pinned) - native/modern modes only |
| `pinned_version` | No | "" | Specific version when resolve_version=pinned - native/modern modes only |
| `license_id` | No | "" | License ID for downloads (pass via secrets) - not required for CINC |
| `base_url_override` | No | "" | Override default base URL (e.g., https://commercial-acceptance.downloads.chef.co for current channel) |
| `hab_ident` | No | "" | Habitat package identifier (e.g., 'core/chef-infra-client') - habitat mode |
| `hab_channel` | No | stable | Habitat channel (stable, current, base-2025, etc.) - habitat mode |
| `hab_origin` | No | "" | Habitat origin (e.g., 'chef') - alternative to hab_ident - habitat mode |
| `hab_auth_token` | No | "" | Habitat Builder Personal Access Token for protected channels (pass via secrets) |
| `out_dir` | No | out | Output directory for results |
| `work_dir` | No | work | Working directory for temporary files |
| `enable_trivy` | No | true | Enable Trivy scanning alongside Grype (native/modern modes only) |
| `trivy_scanners` | No | vuln | Trivy scanner types (comma-separated: vuln, misconfig, secret, license) |
| `trivy_severity` | No | UNKNOWN,LOW,MEDIUM,HIGH,CRITICAL | Severity levels to report |
| `trivy_ignore_unfixed` | No | false | Ignore vulnerabilities without fixes |
| `trivy_timeout` | No | "" | Timeout for Trivy scan |
| `trivy_cache_dir` | No | "" | Directory for Trivy cache |

## Outputs

| Output | Description |
|--------|-------------|
| `resolved_version` | The resolved product version that was scanned |
| `download_url_redacted` | Download URL with license_id removed |

## Size Tracking

**New in 2026**: The action now calculates and tracks the installed size of scanned products.

### Size Metrics

For native and modern modes, the metadata.json includes a `size` section under `target`:

```json
{
  "target": {
    "product": "chef-workstation",
    "channel": "stable",
    "resolved_version": "25.12.1102",
    "download": {...},
    "size": {
      "package_bytes": 134217728,
      "installed_bytes": 536870912,
      "installed_human_readable": "512.00 MB",
      "file_count": 12543
    }
  }
}
```

### Size Fields

- **package_bytes**: Downloaded package size in bytes (compressed .deb file)
- **installed_bytes**: Total size after extraction in bytes (actual disk footprint)
- **installed_human_readable**: Human-readable installed size (e.g., "512.00 MB")
- **file_count**: Number of files after extraction

**For Habitat mode**, size information is tracked differently:
- Each dependency includes its individual installed size
- The index.json includes aggregate totals:
  - **total_installed_bytes**: Combined size of all dependencies
  - **total_installed_human_readable**: Human-readable total size
  - **total_file_count**: Total files across all dependencies

### Use Cases

This size information helps answer:
- **Disk footprint**: How much space does the product consume after installation?
- **CVE scan scope**: What is the actual size of content being scanned for vulnerabilities?
- **Capacity planning**: How much storage is needed for deployments?
- **Trend analysis**: How does installed size change across versions and channels?

### Analysis Tools

Use the provided `calculate_installed_sizes.py` script to analyze sizes across all scanned products:

```bash
python3 calculate_installed_sizes.py
```

This generates a summary table showing package sizes, installed sizes, and file counts for all scanned products.

## Output Files

### Native and Modern Modes

The action generates scanner-specific outputs in the `out_dir/scanners/` directory:

**Scanner Outputs (Canonical):**
- **scanners/grype.latest.json**: Complete Grype scan results
- **scanners/grype.metadata.json**: Grype scan metadata (version, DB info, severity counts)
- **scanners/trivy.latest.json**: Complete Trivy scan results (if enabled)
- **scanners/trivy.metadata.json**: Trivy scan metadata (version, DB info, severity counts)
- **scanners/compare.json**: CVE-level comparison between Grype and Trivy results

**Legacy Compatibility Files:**
For backward compatibility during migration:
- **latest.json**: Copy of `scanners/grype.latest.json`
- **metadata.json**: Copy of `scanners/grype.metadata.json`

**Comparison Format:**
The `compare.json` file provides a CVE-level comparison:
```json
{
  "schema_version": "1.0",
  "generated_at_utc": "2026-02-03T10:15:30Z",
  "target": {
    "product": "chef",
    "channel": "stable",
    "resolved_version": "18.5.0"
  },
  "summary": {
    "grype": {
      "cve_count": 123,
      "severity_counts": {"Critical": 5, "High": 20, ...}
    },
    "trivy": {
      "cve_count": 120,
      "severity_counts": {"Critical": 4, "High": 18, ...}
    }
  },
  "diff": {
    "only_in_grype": ["CVE-2023-1234", ...],
    "only_in_trivy": ["CVE-2023-5678", ...],
    "in_both": ["CVE-2023-9012", ...]
  }
}
```

### Habitat Mode

The action generates an index file and per-dependency scans organized by type:

- **index.json**: Rollup of all dependencies (direct and transitive) with aggregate counts and metadata
- **direct-deps/<origin>/<name>/<version>/<release>.json**: Grype scan results for each direct dependency
- **direct-deps/<origin>/<name>/<version>/<release>.metadata.json**: Metadata for each direct dependency
- **transitive-deps/<origin>/<name>/<version>/<release>.json**: Grype scan results for each transitive dependency
- **transitive-deps/<origin>/<name>/<version>/<release>.metadata.json**: Metadata for each transitive dependency

Example structure:
```
out/
├── index.json
├── direct-deps/
│   ├── core/
│   │   ├── openssl/
│   │   │   └── 3.0.13/
│   │   │       ├── 20250101120000.json
│   │   │       └── 20250101120000.metadata.json
│   │   └── glibc/
│   │       └── 2.39/
│   │           ├── 20250105140500.json
│   │           └── 20250105140500.metadata.json
│   └── chef/
│       └── chef-infra-client/
│           └── 18.5.0/
│               ├── 20250110120000.json
│               └── 20250110120000.metadata.json
└── transitive-deps/
    └── core/
        ├── gcc-libs/
        │   └── 9.5.0/
        │       ├── 20240105173910.json
        │       └── 20240105173910.metadata.json
        └── zlib/
            └── 1.3/
                ├── 20240105173710.json
                └── 20240105173710.metadata.json
```

## Requirements

### Native and Modern Modes
- Ubuntu runner (uses `dpkg` for package extraction)
- Grype is automatically installed if not present
- Trivy is automatically installed if not present
- Valid license_id for the specified download_site:
  - **Commercial**: Requires a commercial license
  - **Community**: Requires a Free license
  - **CINC**: No license required (open source)

### Habitat Mode
- Linux or Windows runner
- Habitat CLI is automatically installed if not present
- Grype is automatically installed if not present
- Valid HAB_AUTH_TOKEN (passed via license_id) for licensed channels

## Download Sites

### Native/Modern Mode
- **Commercial** (`commercial`): Chef commercial downloads at `https://chefdownload-commercial.chef.io`
  - Supports `stable` and `current` channels
  - Requires commercial license_id
- **Community** (`community`): Chef community downloads at `https://chefdownload-community.chef.io`
  - Only supports `stable` channel (API enforced)
  - Requires Free license_id
- **CINC** (`cinc`): Open source Chef at `https://omnitruck.cinc.sh`
  - Only supports `stable` channel
  - No license required
  - Product name mapping: chef→cinc, inspec→cinc-auditor, chef-server→cinc-server, chef-workstation→cinc-workstation

### Habitat Mode
- Channels are flexible: `stable`, `current`, `base-2025`, custom channels, etc.
- Licensed channels (e.g., `base-2025`) require HAB_AUTH_TOKEN via license_id input

## Version Matching Logic

### Smart Stable Channel Selection

When scanning the `stable` channel in native/modern modes, the action implements intelligent major version matching to ensure fair comparisons:

**The Problem**: Comparing `stable` (e.g., v4.18.1) against `current` (e.g., v5.2.0) would show inflated vulnerability differences due to version gap rather than actual security improvements.

**The Solution**: The action automatically:
1. Queries the latest version from the `current` channel
2. Extracts the major version number (e.g., `5` from `5.2.0`)
3. Fetches all available versions from the `stable` channel
4. Selects the highest stable version matching the same major version (e.g., `5.1.0`)

**Example Flow**:
```
Current channel latest: 5.2.0
Stable versions: [4.18.1, 4.18.0, 5.1.0, 5.0.2, 3.22.1]
Selected stable version: 5.1.0 ✅ (matches major version 5)
```

This ensures apples-to-apples comparisons between `stable` and `current` releases, providing meaningful vulnerability trend analysis.

**Fallback Behavior**: If no matching major version is found in stable, the action falls back to using `/versions/latest` from the stable channel.

## Error Handling

The action provides detailed error messages for common failures:
- Missing or expired license_id
- Wrong license type (commercial vs Free)
- Invalid product/channel combinations
- Package download failures

## Example with Multiple Products

```yaml
jobs:
  scan:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        product: [chef, chef-workstation, chef-server]
        channel: [stable, current]
    steps:
      - uses: chef/common-github-actions/.github/actions/chef-download-grype-snapshot@main
        with:
          product: ${{ matrix.product }}
          channel: ${{ matrix.channel }}
          download_site: commercial
          os: ubuntu
          os_version: "24.04"
          arch: x86_64
          scan_root: /opt/${{ matrix.product }}
          license_id: ${{ secrets.GA_DOWNLOAD_GRYPE_LICENSE_ID }}
      
      - name: Upload results
        uses: actions/upload-artifact@v4
        with:
          name: scan-${{ matrix.product }}-${{ matrix.channel }}
          path: out/
```

## Example: Habitat Mode with Multiple Packages

```yaml
jobs:
  habitat-scan:
    runs-on: ubuntu-latest
    strategy:
      matrix:
        package:
          - { ident: "chef/chef-infra-client", channel: "stable" }
          - { ident: "chef/inspec", channel: "stable" }
          - { ident: "core/ruby", channel: "stable" }
    steps:
      - uses: chef/common-github-actions/.github/actions/chef-download-grype-snapshot@main
        with:
          product: ${{ matrix.package.ident }}
          channel: ${{ matrix.package.channel }}
          os: ubuntu
          os_version: "24.04"
          arch: x86_64
          scan_mode: habitat
          hab_ident: ${{ matrix.package.ident }}
          hab_channel: ${{ matrix.package.channel }}
          hab_auth_token: ${{ secrets.HAB_AUTH_TOKEN }}
      
      - name: Upload results
        uses: actions/upload-artifact@v4
        with:
          name: habitat-scan-${{ matrix.package.ident }}-${{ matrix.package.channel }}
          path: out/
```

## Habitat Scan Path Conventions

Habitat packages are scanned at their installation paths:

- **Linux**: `/hab/pkgs/<origin>/<name>/<version>/<release>/`
- **Windows**: `C:\hab\pkgs\<origin>\<name>\<version>\<release>\`

Each dependency is scanned separately, and results are published to the data repo with this structure:

```
habitat/<product>/<channel>/<os>/<arch>/<origin>/<name>/<version>/
├── <release>.json                                          ← Main package scan
├── <release>.metadata.json                                 ← Main package metadata
├── index.json                                              ← Rollup of all dependencies
├── direct-deps/                                            ← Direct dependencies
│   ├── <dep-origin>/<dep-name>/<dep-version>/<dep-release>.json
│   └── <dep-origin>/<dep-name>/<dep-version>/<dep-release>.metadata.json
└── transitive-deps/                                        ← Transitive dependencies
    ├── <dep-origin>/<dep-name>/<dep-version>/<dep-release>.json
    └── <dep-origin>/<dep-name>/<dep-version>/<dep-release>.metadata.json
```

**Example:**
```
habitat/inspec/stable/ubuntu/x86_64/chef/inspec/5.24.5/
├── 20260128071642.json                       ← Main inspec scan
├── 20260128071642.metadata.json              ← Main inspec metadata
├── index.json                                ← Rollup
├── direct-deps/
│   ├── core/ruby31/3.1.7/20250728150529.json
│   ├── core/ruby31/3.1.7/20250728150529.metadata.json
│   ├── core/bash/5.1/20240105214248.json
│   └── core/bash/5.1/20240105214248.metadata.json
└── transitive-deps/
    ├── core/gcc-libs/9.5.0/20240105173910.json
    ├── core/gcc-libs/9.5.0/20240105173910.metadata.json
    ├── core/glibc/2.35/20240105171810.json
    └── core/glibc/2.35/20240105171810.metadata.json
```

## Related Projects

- [chef-vuln-scan-orchestrator](https://github.com/chef/chef-vuln-scan-orchestrator) - Orchestration workflow using this action
- [chef-vuln-scan-data](https://github.com/chef/chef-vuln-scan-data) - Data repository for scan results

# Scan Mode Support

## Native Mode

Native mode downloads and scans Chef product installers from Chef download sites.

### Standard Products
Products like chef, chef-server, and chef-workstation use OS-specific packages:
- **Commercial/Community**: Download URL `?p=ubuntu&pv=24.04&m=x86_64&v=latest`
- **CINC**: Fetches direct .deb URL from `/packages` endpoint (no query params)
- Output path: `native/{product}/{channel}/{download_site}/{os}/{os_version}/{arch}/`

### Download Site Specifics
- **Commercial** (`chefdownload-commercial.chef.io`): Requires license_id, supports stable/current
- **Community** (`chefdownload-community.chef.io`): Requires Free license_id, stable only
- **CINC** (`omnitruck.cinc.sh`): No license, stable only, direct .deb downloads

### Product Name Mapping (CINC only)
CINC uses different product names than Chef:
- `chef` → `cinc`
- `chef-server` → `cinc-server`
- `chef-workstation` → `cinc-workstation`
- `inspec` → `cinc-auditor`

The scanner automatically maps these internally while preserving Chef product names in output paths.

## Modern Mode

Modern mode is for next-generation Chef products with flexible deployment configurations.

### Features
- Supports channel-specific base URLs via `base_url_override`
- Supports channel-specific license IDs
- Universal binaries (no OS version)
- Platform-agnostic packages
- Output path: `modern/{product}/{channel}/{download_site}/{os}/{arch}/{package_manager}/`

### chef-ice Example
- Download URL: `?p=linux&pm=deb&m=x86_64&v=latest` (no OS version)
- Requires `package_manager` input (deb, rpm, or tar)
- Scan root: `/hab` (contains bundled Habitat-based Chef 19)
- Can use different base URLs per channel (e.g., commercial-acceptance for current channel)

## Habitat Mode

Habitat mode installs and scans Habitat packages with per-dependency tracking.

### Features
- Installs Habitat CLI automatically if not present
- Installs specified Habitat package using `hab pkg install`
- Enumerates dependencies (direct and transitive separately)
- Scans each dependency at its install path
- Generates per-dependency JSON and metadata files
- Creates index.json rollup with aggregate counts
- Supports version-based cleanup to prevent historical accumulation
- Modified copy step to handle both native (latest.json/metadata.json) and habitat (index.json/deps/) outputs

### 5. Updated targets.yml
Added example habitat targets:
- chef-habitat-infra-client
- chef-habitat-inspec
- core-habitat-ruby

## Output Structure

### Native Mode (unchanged)
```
out/
├── latest.json
└── metadata.json
```

Published to: `native/<product>/<channel>/<download_site>/<os>/<os_version>/<arch>/`

### Habitat Mode (new)
```
out/
├── index.json
└── deps/
    └── <origin>/
        └── <name>/
            └── <version>/
                ├── <release>.json
                └── <release>.metadata.json
```

Published to: `habitat/<product>/<channel>/<os>/<arch>/`

## Scan Paths

### Linux
- Native: Extracted package directory
- Habitat: `/hab/pkgs/<origin>/<name>/<version>/<release>/`

### Windows
- Habitat: `C:\hab\pkgs\<origin>\<name>\<version>\<release>\`

## Usage Example

```yaml
- uses: chef/common-github-actions/.github/actions/chef-download-grype-snapshot@main
  with:
    product: chef-infra-client
    channel: stable
    os: ubuntu
    os_version: "24.04"
    arch: x86_64
    scan_mode: habitat
    hab_ident: "chef/chef-infra-client"
    hab_channel: stable
    hab_auth_token: ${{ secrets.HAB_AUTH_TOKEN }}
```

## Testing Recommendations

1. Start with `enabled: false` on habitat targets in targets.yml
2. Enable one target at a time for testing
3. Start with direct dependencies only (`transitive_deps: false`)
4. Monitor scan duration and data repo size
5. Add transitive dependencies later if needed

## Implementation Notes

- Habitat CLI is auto-installed using the official install script
- HAB_AUTH_TOKEN is passed via the `license_id` input for licensed channels
- Each dependency is scanned independently to allow granular tracking
- The index.json provides aggregate counts for quick "what changed" comparisons
- Per-dependency metadata enables detailed change tracking

## Benefits

1. **Granular vulnerability tracking**: See which dependency introduced which vulnerability
2. **Change attribution**: Know if vuln count changes are from the main package or a dependency
3. **Dependency awareness**: Track vulnerability landscape across the dependency tree
4. **Consistent structure**: Same JSON schema and metadata approach as native mode
5. **Flexible channels**: Support for stable, current, and custom channels like base-2025
