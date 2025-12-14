# Common Github Actions for Chef organization
Location for reusable workflows

## Naming convention
Typical workflows are stored in the `.github\workflows` directory.

Naming convention:
<workflow type>-<application>-<language>[-<action> || -<branch>][-<stub>].yml

- ci-utility-go-echo.yml
- ci-utility-go-echo-stub.yml - place this in the calling repo

The common GitHub Action with security checks for all Chef repos is 
- ci-main-pull-request.yml (called by ci-main-pull-request-stub.yml)

This performs CI actions - build, test, scan, package - and is described in DEV-README.md

## Supporting files and templates
In the `workflow-supporting-files` you will find the following files:
- Sonar project templates for GoLang, Ruby and Rust, which can becopied as`sonar-project.properties` into the root of a repo and modified
- `.license_scout.yml` contains the default/reference fallback licenses for common Courier items