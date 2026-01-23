# CI/CD Pipeline Workflow Diagram

This document visualizes the CI/CD pipeline workflow, showing each job, the YAML files they call, and the required input variables.

## Pipeline Overview

```mermaid
graph TD
    Start([Pull Request/Push Event]) --> PreCheck[precompilation-checks]
    Start --> Checkout[checkout]
    Start --> GenSlug[generate-filename-slug]
    
    Checkout --> SCC[scc]
    Checkout --> LangSpec[language-specific-checks]
    Checkout --> LangAgn[language-agnostic-checks]
    Checkout --> TruffleHog[run-trufflehog]
    Checkout --> Trivy[run-trivy]
    Checkout --> Build[ci-build]
    Checkout --> Polaris[BlackDuck-Polaris-SAST]
    
    Build --> SetVer[set-application-version]
    Build --> UnitTest[ci-unit-test]
    Build --> SonarPub[Sonar-public-repo]
    Build --> SonarPriv[Sonar-private-repo]
    Build --> SonarInt[Sonar-internal-repo]
    Build --> Package[package-binary]
    Build --> SBOM[generate-sbom]
    
    Package --> Habitat[habitat-build]
    Habitat --> HabPub[habitat-publish]
    HabPub --> GrypeLinux[habitat-grype-scan-linux]
    HabPub --> GrypeWin[habitat-grype-scan-windows]
    Habitat --> Publish[publish]
    
    SBOM --> QualDash[quality-dashboard]
    
    style SCC fill:#e1f5ff
    style TruffleHog fill:#ffe1e1
    style Trivy fill:#ffe1e1
    style Polaris fill:#ffe1e1
    style SonarPub fill:#fff4e1
    style SonarPriv fill:#fff4e1
    style SonarInt fill:#fff4e1
    style SBOM fill:#e1ffe1
    style GrypeLinux fill:#ffe1e1
    style GrypeWin fill:#ffe1e1
```

---

## Detailed Job Mappings

### 1. Source Code Complexity (SCC)

```mermaid
graph LR
    A[scc Job] -->|calls| B[scc.yml]
    B -->|requires| C[Variables]
    
    C -->|input| D[outputfilename: string]
    
    style A fill:#e1f5ff
    style B fill:#d4edff
```

**Workflow File:** `chef/common-github-actions/.github/workflows/scc.yml`

**Required Variables:**
- `outputfilename` (string) - Name of the SCC complexity output file artifact, default: 'scc-complexity'

**Condition:** `inputs.perform-complexity-checks == true`

---

### 2. Secret Scanning (TruffleHog)

```mermaid
graph LR
    A[run-trufflehog Job] -->|calls| B[trufflehog.yml]
    B -->|requires| C[Variables]
    
    C -->|no inputs| D[None Required]
    
    style A fill:#ffe1e1
    style B fill:#ffd4d4
```

**Workflow File:** `chef/common-github-actions/.github/workflows/trufflehog.yml`

**Required Variables:**
- None (inherits secrets automatically)

**Condition:** `inputs.perform-trufflehog-scan == true`

---

### 3. Vulnerability Scanning (Trivy)

```mermaid
graph LR
    A[run-trivy Job] -->|calls| B[trivy.yml]
    B -->|requires| C[Variables]
    
    C -->|input| D[version: string]
    
    style A fill:#ffe1e1
    style B fill:#ffd4d4
```

**Workflow File:** `chef/common-github-actions/.github/workflows/trivy.yml`

**Required Variables:**
- `version` (string) - Version of the project, default: '1.0.0'

**Condition:** `inputs.perform-trivy-scan == true`

---

### 4. BlackDuck Polaris SAST

```mermaid
graph LR
    A[BlackDuck-Polaris-SAST Job] -->|inline steps| B[Inline Implementation]
    B -->|requires| C[Variables]
    
    C -->|secrets| D[POLARIS_SERVER_URL<br/>POLARIS_ACCESS_TOKEN]
    C -->|inputs| E[polaris-application-name<br/>polaris-project-name<br/>polaris-working-directory<br/>polaris-config-path<br/>polaris-coverity-config-path<br/>polaris-coverity-build-command<br/>polaris-coverity-clean-command<br/>polaris-coverity-args<br/>polaris-detect-search-depth<br/>polaris-detect-args<br/>polaris-assessment-mode<br/>wait-for-scan]
    
    style A fill:#ffe1e1
    style B fill:#ffd4d4
```

**Workflow File:** Inline implementation (no separate workflow)

**Required Secrets:**
- `POLARIS_SERVER_URL` - BlackDuck Polaris server URL
- `POLARIS_ACCESS_TOKEN` - BlackDuck Polaris access token
- `GITHUB_TOKEN` - GitHub token for authentication

**Required Variables:**
- `polaris-application-name` (string) - One of: Chef-Agents, Chef-Automate, Chef-Chef360, Chef-Habitat, Chef-Infrastructure-Server, Chef-Shared-Services
- `polaris-project-name` (string) - Typically the repository name

**Optional Variables (New in 1.0.7):**
- `polaris-working-directory` (string) - Working directory for scan
- `polaris-config-path` (string) - Path to Detect configuration file
- `polaris-coverity-config-path` (string) - Path to Coverity configuration file
- `polaris-coverity-build-command` (string) - Coverity build command
- `polaris-coverity-clean-command` (string) - Coverity clean command
- `polaris-coverity-args` (string) - Additional Coverity arguments
- `polaris-detect-search-depth` (string) - Detect search depth, default: '5'
- `polaris-detect-args` (string) - Additional Detect arguments
- `polaris-assessment-mode` (string) - Assessment mode: SAST, CI, or SOURCE_UPLOAD
- `wait-for-scan` (boolean) - Wait for scan completion, default: true

**Condition:** `inputs.perform-blackduck-polaris == true`

---

### 5. SonarQube Scans

#### 5a. SonarQube Public Repository

```mermaid
graph LR
    A[Sonar-public-repo Job] -->|calls| B[sonarqube-public-repo.yml]
    B -->|requires| C[Variables]
    
    C -->|secrets| D[SONAR_TOKEN<br/>SONAR_HOST_URL<br/>AKEYLESS_JWT_ID]
    C -->|inputs| E[perform-build<br/>build-profile<br/>language<br/>report-unit-test-coverage<br/>report-to-atlassian-dashboard<br/>quality-product-name<br/>quality-sonar-app-name<br/>quality-testing-type<br/>quality-service-name<br/>quality-junit-report<br/>visibility<br/>go-private-modules<br/>udf1, udf2, udf3]
    
    style A fill:#fff4e1
    style B fill:#ffe8c5
```

**Workflow File:** `chef/common-github-actions/.github/workflows/sonarqube-public-repo.yml`

**Required Secrets:**
- `SONAR_TOKEN` - SonarQube authentication token
- `SONAR_HOST_URL` - SonarQube server URL (progress.sonar.com)
- `AKEYLESS_JWT_ID` - For Azure firewall rules

**Required Variables:**
- `perform-build` (boolean) - Whether to perform build
- `build-profile` (string) - Build profile, default: 'cli'
- `language` (string) - Programming language
- `report-unit-test-coverage` (boolean) - Report unit test coverage
- `report-to-atlassian-dashboard` (boolean) - Report to QA dashboard
- `quality-product-name` (string) - Product name, default: 'Chef360'
- `quality-sonar-app-name` (string) - Sonar application name
- `quality-testing-type` (string) - Testing type, default: 'Integration'
- `quality-service-name` (string) - Service/repository name
- `quality-junit-report` (string) - Path to JUnit report
- `visibility` (string) - Repository visibility
- `go-private-modules` (string) - GOPRIVATE for Go modules
- `udf1`, `udf2`, `udf3` (string) - User defined flags

**Condition:** `inputs.perform-sonarqube-scan == true && inputs.visibility == 'public'`

#### 5b. SonarQube Private Repository

```mermaid
graph LR
    A[Sonar-private-repo Job] -->|inline steps| B[Inline SonarQube Scan]
    B -->|requires| C[Variables]
    
    C -->|secrets| D[SONAR_TOKEN<br/>SONAR_HOST_URL]
    
    style A fill:#fff4e1
    style B fill:#ffe8c5
```

**Workflow File:** Inline implementation using `sonarsource/sonarqube-scan-action@v5.3.1`

**Required Secrets:**
- `SONAR_TOKEN` - SonarQube authentication token
- `SONAR_HOST_URL` - SonarQube server URL

**Condition:** `inputs.perform-sonarqube-scan == true && inputs.visibility == 'private'`

#### 5c. SonarQube Internal Repository

```mermaid
graph LR
    A[Sonar-internal-repo Job] -->|calls| B[sonarqube-internal-repo.yml]
    B -->|requires| C[Variables]
    
    C -->|secrets| D[SONAR_TOKEN<br/>SONAR_HOST_URL<br/>AKEYLESS_JWT_ID]
    C -->|inputs| E[Same as public repo]
    
    style A fill:#fff4e1
    style B fill:#ffe8c5
```

**Workflow File:** `chef/common-github-actions/.github/workflows/sonarqube-internal-repo.yml`

**Required Variables:** Same as public repository (see 5a)

**Condition:** `inputs.perform-sonarqube-scan == true && inputs.visibility == 'internal'`

---

### 6. SBOM Generation

```mermaid
graph LR
    A[generate-sbom Job] -->|calls| B[sbom.yml]
    B -->|requires| C[Variables]
    
    C -->|secrets| D[BLACKDUCK_SBOM_URL<br/>BLACKDUCK_SCA_TOKEN]
    C -->|inputs| E[version<br/>export-github-sbom<br/>perform-blackduck-sca-scan<br/>blackduck-project-group-name<br/>blackduck-project-name<br/>generate-msft-sbom<br/>license_scout<br/>go-private-modules]
    
    style A fill:#e1ffe1
    style B fill:#c5f5c5
```

**Workflow File:** `chef/common-github-actions/.github/workflows/sbom.yml`

**Required Secrets:**
- `BLACKDUCK_SBOM_URL` - BlackDuck SCA server URL
- `BLACKDUCK_SCA_TOKEN` - BlackDuck SCA authentication token

**Required Variables:**
- `version` (string) - Version of the project
- `export-github-sbom` (boolean) - Export SBOM from GitHub
- `perform-blackduck-sca-scan` (boolean) - Perform BlackDuck SCA scan
- `blackduck-project-group-name` (string) - BlackDuck project group, default: 'Chef'
- `blackduck-project-name` (string) - BlackDuck project name
- `generate-msft-sbom` (boolean) - Generate Microsoft SBOM
- `license_scout` (boolean) - Run license scout
- `go-private-modules` (string) - GOPRIVATE for Go modules

**Condition:** `inputs.generate-sbom == true`

---

### 7. Grype Habitat Package Scanning

#### 7a. Linux Habitat Grype Scan

```mermaid
graph LR
    A[habitat-grype-scan-linux Job] -->|inline steps| B[Install Habitat + Grype]
    B -->|requires| C[Variables]
    
    C -->|secrets| D[HAB_PUBLIC_BLDR_PAT]
    C -->|inputs| E[publish-habitat-hab_package<br/>publish-habitat-hab_version<br/>publish-habitat-hab_release<br/>publish-habitat-hab_channel<br/>publish-habitat-hab_auth_token]
    
    style A fill:#ffe1e1
    style B fill:#ffd4d4
```

**Workflow File:** Inline implementation

**Required Secrets:**
- `HAB_PUBLIC_BLDR_PAT` - Habitat Builder personal access token (fallback)

**Required Variables:**
- `publish-habitat-hab_package` (string) - Habitat package to scan, default: 'core/nginx'
- `publish-habitat-hab_version` (string) - Package version (optional)
- `publish-habitat-hab_release` (string) - Package release (optional)
- `publish-habitat-hab_channel` (string) - Package channel, default: 'stable'
- `publish-habitat-hab_auth_token` (string) - Auth token (optional, uses secret if not provided)

**Condition:** `inputs.habitat-grype-scan == true && inputs.publish-habitat-runner_os == 'ubuntu-latest'`

#### 7b. Windows Habitat Grype Scan

```mermaid
graph LR
    A[habitat-grype-scan-windows Job] -->|inline steps| B[Install Habitat + Grype]
    B -->|requires| C[Variables]
    
    C -->|same as Linux| D[Same variables as Linux]
    
    style A fill:#ffe1e1
    style B fill:#ffd4d4
```

**Workflow File:** Inline implementation

**Required Variables:** Same as Linux version (see 7a)

**Condition:** `inputs.habitat-grype-scan == true && inputs.publish-habitat-runner_os == 'windows-latest'`

---

### 8. Quality Dashboard Reporting

```mermaid
graph LR
    A[quality-dashboard Job] -->|calls| B[irfan-quality-dashboard.yml]
    B -->|requires| C[Variables]
    
    C -->|inputs| D[perform-build<br/>build-profile<br/>language<br/>report-unit-test-coverage<br/>report-to-atlassian-dashboard<br/>quality-product-name<br/>quality-sonar-app-name<br/>quality-testing-type<br/>quality-service-name<br/>quality-junit-report<br/>visibility<br/>go-private-modules<br/>udf1, udf2, udf3]
    
    style A fill:#f0e1ff
    style B fill:#e0c5ff
```

**Workflow File:** `chef/common-github-actions/.github/workflows/irfan-quality-dashboard.yml`

**Required Variables:**
- `perform-build` (boolean) - Whether build was performed
- `build-profile` (string) - Build profile
- `language` (string) - Programming language
- `report-unit-test-coverage` (boolean) - Report unit test coverage
- `report-to-atlassian-dashboard` (boolean) - Report to dashboard
- `quality-product-name` (string) - Product name (Chef360, Courier, InSpec)
- `quality-sonar-app-name` (string) - Sonar application name
- `quality-testing-type` (string) - Testing type (Unit, Integration, e2e, API, Performance, Security)
- `quality-service-name` (string) - Service/repository name
- `quality-junit-report` (string) - Path to JUnit report
- `visibility` (string) - Repository visibility
- `go-private-modules` (string) - GOPRIVATE for Go modules
- `udf1`, `udf2`, `udf3` (string) - User defined flags

**Condition:** `inputs.report-to-atlassian-dashboard == true`

---

## Pipeline Execution Flow

```mermaid
sequenceDiagram
    participant PR as Pull Request
    participant Pre as Pre-checks
    participant Sec as Security Scans
    participant Build as Build & Test
    participant SAST as SAST Scans
    participant Pkg as Package
    participant SBOM as SBOM & SCA
    participant Dash as Dashboard
    
    PR->>Pre: Trigger workflow
    Pre->>Pre: checkout, complexity checks, linting
    Pre->>Sec: TruffleHog, Trivy
    Sec->>Build: Build application, run unit tests
    Build->>SAST: SonarQube, BlackDuck Polaris
    Build->>Pkg: Package binaries, Habitat
    Pkg->>Pkg: Grype scan Habitat packages
    Build->>SBOM: Generate SBOM, BlackDuck SCA
    SBOM->>Dash: Report metrics to Quality Dashboard
```

---

## Summary Table

| Job Name | Workflow File | Type | Key Variables |
|----------|--------------|------|---------------|
| scc | scc.yml | Reusable | outputfilename |
| run-trufflehog | trufflehog.yml | Reusable | None |
| run-trivy | trivy.yml | Reusable | version |
| BlackDuck-Polaris-SAST | Inline | Inline | polaris-application-name, polaris-project-name, +10 optional |
| Sonar-public-repo | sonarqube-public-repo.yml | Reusable | 15 quality/build variables |
| Sonar-private-repo | Inline (sonarsource action) | Inline | SONAR_TOKEN, SONAR_HOST_URL |
| Sonar-internal-repo | sonarqube-internal-repo.yml | Reusable | 15 quality/build variables |
| generate-sbom | sbom.yml | Reusable | version, blackduck settings, sbom flags |
| habitat-grype-scan-linux | Inline | Inline | habitat package details |
| habitat-grype-scan-windows | Inline | Inline | habitat package details |
| quality-dashboard | irfan-quality-dashboard.yml | Reusable | 15 quality/reporting variables |

---

## Legend

- 🔵 **Blue** - Complexity/Code Quality
- 🔴 **Red** - Security Scans
- 🟡 **Yellow** - SAST Tools
- 🟢 **Green** - SBOM/SCA
- 🟣 **Purple** - Reporting/Dashboard

---

## Notes

1. **Inline vs Reusable Workflows**: Some jobs call reusable workflows (`.yml` files), while others execute steps inline within the main workflow.

2. **Conditional Execution**: Most jobs have conditions based on input flags (e.g., `inputs.perform-trufflehog-scan`).

3. **Secrets Management**: Secrets are inherited via `secrets: inherit` or explicitly passed for specific actions.

4. **Dependencies**: Jobs use `needs:` to establish execution order (e.g., most scans need `checkout` first).

5. **Parallel Execution**: Jobs without dependencies can run in parallel (e.g., TruffleHog and Trivy can run simultaneously).
