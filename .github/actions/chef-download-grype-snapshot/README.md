# Chef Download + Grype Snapshot Action

Composite action that downloads Chef products and runs Grype vulnerability scans.

Supports two scan modes:
- **native**: Downloads packages from downloads.chef.io and scans them
- **habitat**: Installs Habitat packages and scans each dependency separately

## Usage

### Native Mode

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
    license_id: ${{ secrets.LICENSE_ID }}
```

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `product` | Yes | - | Chef product name (chef, chef-workstation, chef-server, etc.) |
| `channel` | Yes | - | Release channel (stable, current) or target channel for native/habitat |
| `download_site` | Yes | commercial | Download site (commercial or community) - native mode only |
| `os` | Yes | ubuntu | OS platform |
| `os_version` | Yes | - | OS version (e.g., 24.04) |
| `arch` | Yes | x86_64 | Architecture |
| `scan_mode` | Yes | native | Scan mode (native or habitat) |
| `scan_root` | Yes | - | Install root path for metadata (e.g., /opt/chef) - native mode only |
| `resolve_version` | Yes | latest | Version resolution (latest or pinned) - native mode only |
| `pinned_version` | No | "" | Specific version when resolve_version=pinned - native mode only |
| `license_id` | No | "" | License ID for downloads (pass via secrets) |
| `hab_ident` | No | "" | Habitat package identifier (e.g., 'core/chef-infra-client') - habitat mode |
| `hab_channel` | No | stable | Habitat channel (stable, current, base-2025, etc.) - habitat mode |
| `hab_origin` | No | "" | Habitat origin (e.g., 'chef') - alternative to hab_ident - habitat mode |
| `transitive_deps` | No | false | Include transitive dependencies in habitat scan (true/false) |
| `out_dir` | No | out | Output directory for results |
| `work_dir` | No | work | Working directory for temporary files |

## Outputs

| Output | Description |
|--------|-------------|
| `resolved_version` | The resolved product version that was scanned |
| `download_url_redacted` | Download URL with license_id removed |

## Output Files

### Native Mode

The action generates two JSON files in the `out_dir`:

- **latest.json**: Complete Grype scan results
- **metadata.json**: Scan metadata including version, environment, and severity counts

### Habitat Mode

The action generates an index file and per-dependency scans:

- **index.json**: Rollup of all dependencies with aggregate counts and metadata
- **deps/<origin>/<name>/<version>/<release>.json**: Grype scan results for each dependency
- **deps/<origin>/<name>/<version>/<release>.metadata.json**: Metadata for each dependency scan

Example structure:
```
out/
├── index.json
└── deps/
    ├── core/
    │   ├── openssl/
    │   │   └── 3.0.13/
    │   │       ├── 20250101120000.json
    │   │       └── 20250101120000.metadata.json
    │   └── glibc/
    │       └── 2.39/
    │           ├── 20250105140500.json
    │           └── 20250105140500.metadata.json
    └── chef/
        └── chef-infra-client/
            └── 18.5.0/
                ├── 20250110120000.json
                └── 20250110120000.metadata.json
```

## Requirements

### Native Mode
- Ubuntu runner (uses `dpkg` for package extraction)
- Grype is automatically installed if not present
- Valid license_id for the specified download_site:
  - Commercial sites require a commercial license
  - Community sites require a Free license

### Habitat Mode
- Linux or Windows runner
- Habitat CLI is automatically installed if not present
- Grype is automatically installed if not present
- Valid HAB_AUTH_TOKEN (passed via license_id) for licensed channels

## Download Site Constraints

### Native Mode
- **Commercial**: Supports both `stable` and `current` channels
- **Community**: Only supports `stable` channel (API enforced)

### Habitat Mode
- Channels are flexible: `stable`, `current`, `base-2025`, custom channels, etc.
- Licensed channels (e.g., `base-2025`) require HAB_AUTH_TOKEN via license_id input

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
          license_id: ${{ secrets.HAB_AUTH_TOKEN }}
          transitive_deps: false
      
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
habitat/<product>/<channel>/<os>/<arch>/index.json
habitat/<product>/<channel>/<os>/<arch>/deps/<origin>/<name>/<version>/<release>.json
habitat/<product>/<channel>/<os>/<arch>/deps/<origin>/<name>/<version>/<release>.metadata.json
```

## Related Projects

- [chef-vuln-scan-orchestrator](https://github.com/chef/chef-vuln-scan-orchestrator) - Orchestration workflow using this action
- [chef-vuln-scan-data](https://github.com/chef/chef-vuln-scan-data) - Data repository for scan results

# Habitat Scan Mode Support

## Overview

The chef-download-grype-snapshot action now supports scanning Habitat packages in addition to native installers. This enables separate vulnerability tracking for each dependency in a Habitat package.

## Changes Made

### 1. Updated run.py
- Added habitat scan mode that:
  - Installs Habitat CLI automatically if not present
  - Installs the specified Habitat package using `hab pkg install`
  - Enumerates dependencies (direct or transitive)
  - Scans each dependency separately at its install path
  - Generates per-dependency JSON and metadata files
  - Creates an index.json rollup with aggregate counts

### 2. Updated action.yml
Added new inputs for habitat mode:
- `hab_ident`: Habitat package identifier (e.g., 'core/chef-infra-client')
- `hab_channel`: Habitat channel (stable, current, base-2025, etc.)
- `hab_origin`: Alternative to hab_ident for specifying origin
- `transitive_deps`: Include transitive dependencies (true/false)

### 3. Updated README.md
- Added habitat mode usage examples
- Documented new inputs
- Explained output file structure for habitat mode
- Added Habitat scan path conventions

### 4. Updated nightly-snapshot.yml
- Extended matrix generation to pass habitat-specific parameters
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
    transitive_deps: false
    license_id: ${{ secrets.HAB_AUTH_TOKEN }}
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
