# CI/CD Security and Quality Scanning Tools

This document describes the security and quality scanning tools configured in the CI/CD pipeline.

---

## Code Quality & Complexity

### **SCC (Source Code Complexity)**
**Purpose:** Analyzes source code complexity metrics including lines of code, cyclomatic complexity, and comment ratios across multiple programming languages.

**What it scans:** 
- Lines of code (physical, logical, comments)
- Cyclomatic complexity
- Code structure and organization

**Reporting:**
- Generates a text output file (default: `scc-complexity.txt`)
- Uploaded as a GitHub Actions artifact
- Used to track code maintainability over time

---

## Language-Specific Analysis

### **Linting Tools**
**Purpose:** Perform language-specific code quality checks and enforce coding standards.

**Supported Languages:**
- **Go**: golangci-lint, staticcheck
- **Ruby**: RuboCop
- **Rust**: Clippy

**What they scan:**
- Code style violations
- Potential bugs
- Performance issues
- Best practice violations

**Reporting:**
- Console output in GitHub Actions logs
- Can fail the build based on severity

---

## Secret Scanning

### **TruffleHog**
**Purpose:** Scans for accidentally committed secrets, credentials, and sensitive information in source code and git history.

**What it scans:**
- API keys and tokens
- Passwords
- Private keys
- Database connection strings
- Cloud provider credentials

**Reporting:**
- Results displayed in GitHub Actions logs
- Can be configured to fail the build if secrets are found
- Integrated findings available through the workflow

---

## Vulnerability Scanning

### **Trivy**
**Purpose:** Comprehensive security scanner for vulnerabilities in dependencies, container images, and infrastructure as code.

**What it scans:**
- OS packages and dependencies
- Application dependencies (npm, pip, gem, etc.)
- Container images
- Infrastructure as Code (IaC) misconfigurations

**Reporting:**
- JSON/SARIF output formats
- Results uploaded as GitHub Actions artifacts
- Integration with GitHub Security tab (if SARIF format enabled)

---

## Static Application Security Testing (SAST)

### **BlackDuck Polaris (Coverity)**
**Purpose:** Enterprise-grade static analysis for identifying security vulnerabilities and code quality issues in source code.

**What it scans:**
- Security vulnerabilities (CWE/OWASP categories)
- Code quality defects
- Compliance violations
- API misuse

**Configuration:**
- Application name: Maps to Chef product (e.g., Chef-Chef360, Chef-Habitat)
- Project name: Typically the repository name
- Assessment modes: SAST, CI, or SOURCE_UPLOAD
- Configurable build commands and scan depth

**Reporting:**
- Results available at: `https://polaris.blackduck.com`
- Project-specific dashboard with vulnerability details
- Can block builds based on policy violations
- SARIF reports can be uploaded to GitHub Security

---

### **SonarQube**
**Purpose:** Continuous code quality and security inspection platform that identifies bugs, code smells, and security vulnerabilities.

**What it scans:**
- Security vulnerabilities
- Code smells and maintainability issues
- Code coverage from unit tests
- Duplicate code
- Technical debt

**Configuration:**
- Separate workflows for public, private, and internal repositories
- Integrates with unit test coverage reports
- Language-specific analysis rules

**Reporting:**
- Results available at configured SonarQube server (progress.sonar.com)
- Quality Gate status (pass/fail)
- Detailed metrics on code quality, security, and coverage
- Historical trends and project comparison

---

## Software Composition Analysis (SCA)

### **BlackDuck SCA (Sbominator)**
**Purpose:** Identifies open source components, licenses, and known vulnerabilities in dependencies.

**What it scans:**
- Open source dependencies
- License compliance
- Known vulnerabilities (CVEs)
- Component versions and updates

**Configuration:**
- Project group: Maps to Chef product groups
- Project name: Typically repository name
- Requires version specification for accurate tracking

**Reporting:**
- Results at: `https://progresssoftware.app.blackduck.com`
- SBOM generation in SPDX format
- License compliance reports
- Vulnerability risk analysis
- Policy violation alerts

---

### **Grype (Habitat Package Scanning)**
**Purpose:** Vulnerability scanner specifically used for scanning built Habitat packages.

**What it scans:**
- Installed packages within Habitat artifacts
- Known CVEs in package dependencies
- OS-level vulnerabilities

**Reporting:**
- Text output files uploaded as GitHub Actions artifacts
- Separate scans for Linux and Windows platforms
- Results named: `grype-results-{platform}-{package}.txt`

---

## Software Bill of Materials (SBOM)

### **GitHub SBOM Export**
**Purpose:** Generates and exports SPDX-compliant SBOM for dependency tracking.

**What it includes:**
- All project dependencies
- Component versions
- License information
- Package relationships

**Reporting:**
- SPDX JSON format
- Uploaded as GitHub Actions artifact
- Can be submitted to BlackDuck SCA for analysis

---

### **Microsoft SBOM Tool**
**Purpose:** Alternative SBOM generation using Microsoft's tooling.

**What it includes:**
- SPDX 2.2 format
- Component inventory
- License data

**Reporting:**
- JSON artifacts uploaded to workflow
- Integration with supply chain security tools

---

### **License Scout**
**Purpose:** Scans project dependencies for license compliance using `.license_scout.yml` configuration.

**What it scans:**
- Dependency licenses
- License compatibility
- Compliance violations

**Reporting:**
- License compliance report
- Violations flagged based on policy

---

## Quality Dashboard Integration

### **Atlassian Quality Dashboard**
**Purpose:** Aggregates quality metrics from multiple sources for centralized reporting.

**Data Sources:**
- SonarQube metrics
- Unit test results (JUnit format)
- Code coverage data

**Reported Metrics:**
- Product: Chef-360, Courier, InSpec, etc.
- Service/Repository name
- Testing type: Unit, Integration, e2e, API, Performance, Security
- Quality gate status

**Reporting:**
- Centralized dashboard (Irfan's QA dashboard)
- Historical trend analysis
- Cross-project comparison

---

## Container Security

### **Docker Scan**
**Purpose:** Scans Dockerfiles and built container images for vulnerabilities and misconfigurations.

**Tools Used:**
- Docker Scout
- Trivy (can also scan containers)

**What it scans:**
- Base image vulnerabilities
- Layer-specific issues
- Dockerfile best practices
- Container configuration

**Reporting:**
- Results in GitHub Actions logs
- Uploaded artifacts for detailed analysis

---

## Summary Table

| Tool | Type | Primary Use | Output Location |
|------|------|-------------|-----------------|
| SCC | Complexity | Code metrics | GitHub Artifacts |
| TruffleHog | Secret Scan | Credential detection | Actions Logs |
| Trivy | Vulnerability | Dependencies & containers | GitHub Artifacts/Security |
| BlackDuck Polaris | SAST | Security vulnerabilities | polaris.blackduck.com |
| SonarQube | SAST/Quality | Code quality & security | progress.sonar.com |
| BlackDuck SCA | SCA | License & vulnerabilities | progresssoftware.app.blackduck.com |
| Grype | Vulnerability | Habitat packages | GitHub Artifacts |
| SBOM Tools | Compliance | Dependency inventory | GitHub Artifacts |
| Quality Dashboard | Reporting | Aggregated metrics | Atlassian Dashboard |
