# Chef Automate Container - Dockerfile for Scanning
# Based on Ubuntu 25.10 with systemd support for Chef Automate deployment
FROM ubuntu:25.10

# Avoid interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Update package list and install dependencies
# Combine RUN commands to reduce layers and improve caching
RUN apt-get update && apt-get install -y \
    bash \
    curl \
    wget \
    ca-certificates \
    unzip \
    systemd \
    systemd-sysv \
    python3 \
    jq \
    && rm -rf /var/lib/apt/lists/*

# Download and install Chef Automate CLI
# Reference: https://docs.chef.io/automate/install/
RUN curl -L https://packages.chef.io/files/current/latest/chef-automate-cli/chef-automate_linux_amd64.zip \
    -o chef-automate.zip \
    && unzip chef-automate.zip \
    && chmod +x chef-automate \
    && rm chef-automate.zip

# Install Grype vulnerability scanner
# Using official Anchore installation script
RUN curl -sSfL https://raw.githubusercontent.com/anchore/grype/main/install.sh \
    | sh -s -- -b /usr/local/bin

# Verify installations
RUN ./chef-automate version && grype version

# Set working directory
WORKDIR /root

# Entry point must be systemd for Automate to deploy properly
# Chef Automate requires systemd to manage services (PostgreSQL, Elasticsearch, etc.)
# Container must be run with --privileged and proper cgroup mounts:
#   docker run -d --privileged --cgroupns=host -v /sys/fs/cgroup:/sys/fs/cgroup:rw automate:latest
ENTRYPOINT ["/lib/systemd/systemd"]

# Metadata labels
LABEL maintainer="Chef Software <info@chef.io>"
LABEL description="Chef Automate container with Grype for vulnerability scanning"
LABEL version="1.0"
