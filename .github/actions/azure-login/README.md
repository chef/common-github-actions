# azure-key-vault-login

Action for setting up the access to the Azure.

## Inputs

- `akeyless-access-id` - The access id for your auth method.

## Outputs

- `TenantId` - The tenant id of the Azure resource group used for the Progress certificate.
- `AppId` - The app id (user id) of the Azure resource group used for the Progress certificate.
- `SecretText` - The password for access to the Azure resource group used for the Progress certificate.

## How to use

Setting up the action requires admin access to the your organization on GitHub and to the your workspace in Akeyless.

1. Add the repository to the list of `repository` sub claims in the access role.
1. Add the `AKEYLESS_JWT_ID` organization secret to your repository if not set by default.
1. Invoke the action in your workflow. Here's an example:

```yml
name: Setup Azure Login

on:
  workflow_dispatch:

jobs:
  build:
    runs-on: ubuntu-latest

    # Required for Akeyless authentication
    permissions: 
      id-token: write
      contents: read

    steps:
      - name: Checkout
        uses: actions/checkout@v3

      - name: Prepare and Login into Azure
        id: get-aad-secret
        uses: ~/.github/actions/azure-login@develop
        with:
          akeyless-access-id: '${{ secrets.AKEYLESS_JWT_ID }}'

        # we must add the runner's ip to the azure firewall rule in order to be able to use the progress certificate
      - name: add runner ip to firewall list
        uses: ~/.github/actions/update-firewall-rule@develop
        with:
          action-to-execute: add
```

After the signing step you must add:

```yml

      - name: Remove Storage Firewall Rule
        if: always()
        uses: ~/.github/actions/update-firewall-rule@develop
        with:
          action-to-execute: remove
      - name: logout
        if: always()
        shell: bash
        run: |
          az logout

```

More information about the action used for getting dynamic secrets from akeyless you can find here: https://github.com/marketplace/actions/akeyless-aad-dynamic-secret
