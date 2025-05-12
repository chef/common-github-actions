# Update NSG Firewall Rule

Action for adding/removing runner's ip to a Azure NSG firewall list.

## Inputs

- `action-to-execute` - Define the type of action to be executed: add or remove.

## Outputs

The action doesn't export any outputs.

## How to use

- Invoke the action in your workflow. Here's an example for adding an ip:

```yml
name: Add NSG Firewall Rule

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

      - name: Add Storage Firewall Rule
        if: always()
        uses: ~/.github/actions/update-firewall-rule@develop
        with:
          action-to-execute: add
```

- Invoke the action in your workflow. Here's an example for removing already added ip:

```yml
name: Remove NSG Firewall Rule

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

      - name: Remove Storage Firewall Rule
        if: always()
      uses: ~/.github/actions/update-firewall-rule@develop
        with:
          action-to-execute: remove
```
