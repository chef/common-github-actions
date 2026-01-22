# Chef Download + Grype Snapshot Action

Composite action that downloads Chef products from downloads.chef.io and runs Grype vulnerability scans.

## Usage

```yaml
- name: Scan chef product
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

## Inputs

| Input | Required | Default | Description |
|-------|----------|---------|-------------|
| `product` | Yes | - | Chef product name (chef, chef-workstation, chef-server, etc.) |
| `channel` | Yes | - | Release channel (stable, current) |
| `download_site` | Yes | commercial | Download site (commercial or community) |
| `os` | Yes | ubuntu | OS platform |
| `os_version` | Yes | - | OS version (e.g., 24.04) |
| `arch` | Yes | x86_64 | Architecture |
| `scan_mode` | Yes | native | Scan mode (native or habitat) |
| `scan_root` | Yes | - | Install root path for metadata (e.g., /opt/chef) |
| `resolve_version` | Yes | latest | Version resolution (latest or pinned) |
| `pinned_version` | No | "" | Specific version when resolve_version=pinned |
| `license_id` | No | "" | License ID for downloads (pass via secrets) |
| `out_dir` | No | out | Output directory for results |
| `work_dir` | No | work | Working directory for temporary files |

## Outputs

| Output | Description |
|--------|-------------|
| `resolved_version` | The resolved product version that was scanned |
| `download_url_redacted` | Download URL with license_id removed |

## Output Files

The action generates two JSON files in the `out_dir`:

- **latest.json**: Complete Grype scan results
- **metadata.json**: Scan metadata including version, environment, and severity counts

## Requirements

- Ubuntu runner (uses `dpkg` for package extraction)
- Grype is automatically installed if not present
- Valid license_id for the specified download_site:
  - Commercial sites require a commercial license
  - Community sites require a Free license

## Download Site Constraints

- **Commercial**: Supports both `stable` and `current` channels
- **Community**: Only supports `stable` channel (API enforced)

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

## Related Projects

- [chef-vuln-scan-orchestrator](https://github.com/chef/chef-vuln-scan-orchestrator) - Orchestration workflow using this action
- [chef-vuln-scan-data](https://github.com/chef/chef-vuln-scan-data) - Data repository for scan results
