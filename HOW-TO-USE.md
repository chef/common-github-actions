# HOW-TO-USE: Chef Common GitHub Actions

This guide explains how to use the reusable workflows from the `chef/common-github-actions` repository in your own projects.

> **📖 For detailed pipeline architecture, tool reference, and mermaid diagrams, see [PIPELINE-REFERENCE.md](PIPELINE-REFERENCE.md)**

---

## Table of Contents

- [Quick Start](#quick-start)
- [Versioning with Tags](#versioning-with-tags)
- [Available Workflows](#available-workflows)
- [Required Secrets](#required-secrets)
- [Configuration Examples](#configuration-examples)
- [Input Reference](#input-reference)

---

## Quick Start

### Step 1: Copy the Stub Workflow

Copy the stub file to your repository's `.github/workflows/` directory:

```yaml
# .github/workflows/ci-main-pull-request.yml
name: CI Pull Request on Main Branch

on: 
  pull_request:
    branches: [ main, release/** ]
  push:
    branches: [ main, release/** ]
  workflow_dispatch:

permissions:
  contents: read
  
jobs: 
  call-ci-main-pr-check-pipeline:
    # Pin to a specific version for stability
    uses: chef/common-github-actions/.github/workflows/ci-main-pull-request.yml@v1.0.7
    secrets: inherit
    permissions: 
      id-token: write
      contents: read
    with:   
      visibility: ${{ github.event.repository.visibility }}
      language: 'go'  # go, ruby, rust
      perform-complexity-checks: true
      perform-trufflehog-scan: true
      perform-trivy-scan: true
      perform-sonarqube-scan: true
      generate-sbom: true
```

### Step 2: Configure Required Secrets

Ensure your repository or organization has the required secrets configured. See [Required Secrets](#required-secrets) below.

### Step 3: Add sonar-project.properties

Copy the appropriate template from `workflow-supporting-files/sonar-templates/` to your repository root:

```bash
# For Go projects
cp GO-sonar-project.properties sonar-project.properties

# For Ruby projects
cp RUBY-sonar-project.properties sonar-project.properties

# For Rust projects
cp RUST-sonar-project.properties sonar-project.properties
```

---

## Versioning with Tags

The `common-github-actions` repository uses semantic versioning tags to allow projects to reference specific versions:

```yaml
# Reference a specific version (recommended for stability)
uses: chef/common-github-actions/.github/workflows/ci-main-pull-request.yml@v1.0.7

# Reference the latest from main (use with caution)
uses: chef/common-github-actions/.github/workflows/ci-main-pull-request.yml@main
```

### Tag Format

Tags follow semantic versioning: `v{MAJOR}.{MINOR}.{PATCH}`

| Bump Type | When to Use |
|-----------|-------------|
| **MAJOR** | Breaking changes |
| **MINOR** | New features, backward compatible |
| **PATCH** | Bug fixes, backward compatible |

### Automatic Tagging

When code is merged to `main` in `common-github-actions`, a new patch tag is automatically created via the `create-release-tag.yml` workflow. Manual version bumps can be triggered via workflow dispatch.

---

## Available Workflows

| Workflow | Purpose | File |
|----------|---------|------|
| CI Main Pull Request | Complete CI pipeline with security scans | `ci-main-pull-request.yml` |
| Create Release Tag | Auto-tag on merge to main | `create-release-tag.yml` |
| SCC | Source code complexity analysis | `scc.yml` |
| TruffleHog | Secret scanning | `trufflehog.yml` |
| Trivy | Vulnerability scanning | `trivy.yml` |
| SonarQube (Public) | SAST for public repos | `sonarqube-public-repo.yml` |
| SonarQube (Internal) | SAST for internal repos | `sonarqube-internal-repo.yml` |
| SBOM | Software Bill of Materials | `sbom.yml` |
| Quality Dashboard | Atlassian quality reporting | `irfan-quality-dashboard.yml` |

> **See [PIPELINE-REFERENCE.md](PIPELINE-REFERENCE.md) for detailed documentation on each tool, including workflow diagrams and job mappings.**

---

## Required Secrets

Configure these secrets at the repository or organization level:

| Secret | Used By | Purpose |
|--------|---------|---------|
| `SONAR_TOKEN` | SonarQube | Authentication token |
| `SONAR_HOST_URL` | SonarQube | Server URL (progress.sonar.com) |
| `AKEYLESS_JWT_ID` | SonarQube | Azure firewall rules (public/internal) |
| `POLARIS_SERVER_URL` | BlackDuck Polaris | Server URL |
| `POLARIS_ACCESS_TOKEN` | BlackDuck Polaris | Authentication token |
| `BLACKDUCK_SBOM_URL` | BlackDuck SCA | Server URL |
| `BLACKDUCK_SCA_TOKEN` | BlackDuck SCA | Authentication token |
| `HAB_PUBLIC_BLDR_PAT` | Habitat/Grype | Builder access token |
| `GH_TOKEN` | Go modules | Private module access |

---

## Configuration Examples

### Go Project (CLI Application)

```yaml
name: CI Pipeline

on:
  pull_request:
    branches: [ main ]
  push:
    branches: [ main ]

jobs:
  ci:
    uses: chef/common-github-actions/.github/workflows/ci-main-pull-request.yml@v1.0.7
    secrets: inherit
    permissions:
      id-token: write
      contents: read
    with:
      visibility: ${{ github.event.repository.visibility }}
      language: 'go'
      version: '1.0.0'
      build-profile: 'cli'
      
      # Code Quality
      perform-complexity-checks: true
      perform-language-linting: true
      
      # Security Scans
      perform-trufflehog-scan: true
      perform-trivy-scan: true
      perform-sonarqube-scan: true
      
      # BlackDuck Polaris
      perform-blackduck-polaris: true
      polaris-application-name: 'Chef-Chef360'
      polaris-project-name: ${{ github.event.repository.name }}
      polaris-assessment-mode: 'SAST'
      
      # Build
      build: true
      unit-tests: true
      
      # SBOM
      generate-sbom: true
      perform-blackduck-sca-scan: true
      blackduck-project-group-name: 'Chef-Chef360'
```

### Ruby Project (Gem)

```yaml
jobs:
  ci:
    uses: chef/common-github-actions/.github/workflows/ci-main-pull-request.yml@v1.0.7
    secrets: inherit
    permissions:
      id-token: write
      contents: read
    with:
      visibility: ${{ github.event.repository.visibility }}
      language: 'ruby'
      version: '1.0.0'
      
      perform-complexity-checks: true
      perform-language-linting: true
      perform-trufflehog-scan: true
      perform-trivy-scan: true
      perform-sonarqube-scan: true
      
      build: true
      unit-tests: true
      run-bundle-install: true  # For projects without committed Gemfile.lock
      
      generate-sbom: true
      license_scout: true
```

### Habitat Package

```yaml
jobs:
  ci:
    uses: chef/common-github-actions/.github/workflows/ci-main-pull-request.yml@v1.0.7
    secrets: inherit
    permissions:
      id-token: write
      contents: read
    with:
      visibility: ${{ github.event.repository.visibility }}
      language: 'rust'
      
      perform-trufflehog-scan: true
      perform-trivy-scan: true
      
      # Packaging
      package-binaries: true
      habitat-build: true
      publish-habitat-packages: true
      publish-habitat-hab_package: 'myorg/mypackage'
      publish-habitat-hab_channel: 'stable'
      habitat-grype-scan: true
      
      generate-sbom: true
```

### Minimal Security Scan Only

```yaml
jobs:
  security:
    uses: chef/common-github-actions/.github/workflows/ci-main-pull-request.yml@v1.0.7
    secrets: inherit
    with:
      visibility: ${{ github.event.repository.visibility }}
      language: 'go'
      
      # Disable everything except security scans
      perform-complexity-checks: false
      perform-language-linting: false
      build: false
      unit-tests: false
      package-binaries: false
      habitat-build: false
      generate-sbom: false
      report-to-atlassian-dashboard: false
      
      # Enable security scans only
      perform-trufflehog-scan: true
      perform-trivy-scan: true
```

---

## Input Reference

### Core Inputs

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `visibility` | string | `public` | Repository visibility (public/private/internal) |
| `language` | string | `ruby` | Build language (go/ruby/rust) |
| `version` | string | `1.0.0` | Project version |
| `go-private-modules` | string | `github.com/progress-platform-services/*` | GOPRIVATE setting |

### Security Scan Flags

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `perform-complexity-checks` | boolean | `true` | Run SCC complexity checks |
| `perform-language-linting` | boolean | `true` | Run language-specific linting |
| `perform-trufflehog-scan` | boolean | `true` | Run TruffleHog secret scan |
| `perform-trivy-scan` | boolean | `true` | Run Trivy vulnerability scan |
| `perform-sonarqube-scan` | boolean | `true` | Run SonarQube scan |
| `perform-blackduck-polaris` | boolean | `false` | Run BlackDuck Polaris SAST |
| `perform-docker-scan` | boolean | `false` | Run Docker scan |

### Build Configuration

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `build` | boolean | `true` | Run CI build |
| `build-profile` | string | `cli` | Build profile |
| `unit-tests` | boolean | `true` | Run unit tests |
| `run-bundle-install` | boolean | `false` | Run bundle install (Ruby) |

### BlackDuck Polaris

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `polaris-application-name` | string | - | Application name (Chef-Chef360, etc.) |
| `polaris-project-name` | string | repo name | Project name |
| `polaris-working-directory` | string | `.` | Working directory |
| `polaris-assessment-mode` | string | `CI` | Mode (SAST/CI/SOURCE_UPLOAD) |
| `wait-for-scan` | boolean | `true` | Wait for scan completion |

### SBOM & SCA

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `generate-sbom` | boolean | `true` | Generate SBOM |
| `export-github-sbom` | boolean | `true` | Export GitHub SBOM |
| `generate-msft-sbom` | boolean | `true` | Generate Microsoft SBOM |
| `license_scout` | boolean | `true` | Run license scout |
| `perform-blackduck-sca-scan` | boolean | `false` | Run BlackDuck SCA scan |
| `blackduck-project-group-name` | string | `Chef` | BlackDuck project group |
| `blackduck-project-name` | string | repo name | BlackDuck project name |

### Habitat Packaging

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `package-binaries` | boolean | `true` | Package binaries |
| `habitat-build` | boolean | `true` | Create Habitat packages |
| `publish-habitat-packages` | boolean | `false` | Publish to Builder |
| `publish-habitat-hab_package` | string | `core/nginx` | Package name |
| `publish-habitat-hab_channel` | string | `stable` | Channel |
| `habitat-grype-scan` | boolean | `false` | Scan with Grype |

### Quality Dashboard

| Input | Type | Default | Description |
|-------|------|---------|-------------|
| `report-to-atlassian-dashboard` | boolean | `true` | Report to dashboard |
| `report-unit-test-coverage` | boolean | `true` | Report coverage |
| `quality-product-name` | string | `Chef360` | Product name |

> **For a complete list of all inputs with detailed descriptions, see [PIPELINE-REFERENCE.md](PIPELINE-REFERENCE.md)**

---

## Support

For issues or questions:

1. Check [PIPELINE-REFERENCE.md](PIPELINE-REFERENCE.md) for detailed tool documentation
2. Review [DEV-README.md](.github/workflows/DEV-README.md) for development notes
3. Open an issue in this repository

---

## Version History

| Version | Date | Changes |
|---------|------|---------|
| v1.0.7 | 2025 | Added Polaris configuration options, Go build/test, Habitat Grype scanning |
| v1.0.5 | 2024 | Initial release with core security scanning |
