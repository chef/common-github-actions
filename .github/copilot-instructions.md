# Copilot Instructions

## GitHub Actions Workflow Security

### Secret Exposure Prevention

1. **Delete any lines that attempt to echo secrets** *(applies to GitHub Actions workflow files — `.yml`/`.yaml` files under `.github/workflows/`)***.**
   When editing or generating workflow files, remove any `run` step lines that print secret values to output, such as:
   ```yaml
   # These patterns must be removed:
   run: echo ${{ secrets.MY_SECRET }}
   run: echo "${{ secrets.MY_SECRET }}"
   run: echo '${{ secrets.MY_SECRET }}'
   ```
   This applies to `echo`, `print`, `Write-Output`, `Write-Host`, or any other command that outputs a secret value.

2. **Warn when secrets other than `GITHUB_TOKEN` are accessed** *(applies to GitHub Actions workflow files)***.**
   If a workflow references `secrets.*` for any secret other than `secrets.GITHUB_TOKEN`, add a comment warning immediately above the reference:
   ```yaml
   # WARNING: This workflow accesses a non-default secret. Ensure this secret is
   # required and that it is stored securely in the repository or organization settings.
   - name: Some step
     env:
       MY_TOKEN: ${{ secrets.MY_CUSTOM_SECRET }}
   ```
   `secrets.GITHUB_TOKEN` is automatically provisioned by GitHub and does not require a warning.
