# GitHub Actions Azure OIDC

The frontend and backend deployment jobs authenticate only from the `main`
branch. GitHub therefore issues an OIDC token with this exact subject:

```text
repo:VedantDeveloper2005/ZeroOps-AI:ref:refs/heads/main
```

The checked-in [federated credential manifest](../.azure/federated-credential.json)
is a provisioning input. Editing it does not update Microsoft Entra.

## Required one-time Entra configuration

After an interactive administrator login, apply the manifest to every Entra
application whose client ID can be selected by either deployment workflow:

```powershell
$tenantId = "<Microsoft Entra tenant ID>"
$subscriptionId = "<Azure subscription ID>"

az login --tenant $tenantId
az account set --subscription $subscriptionId

$frontendClientId = "<frontend deployment application client ID>"
$backendClientId = "<backend deployment application client ID>"

az ad app federated-credential create `
  --id $frontendClientId `
  --parameters .azure/federated-credential.json

if ($backendClientId -ne $frontendClientId) {
  az ad app federated-credential create `
    --id $backendClientId `
    --parameters .azure/federated-credential.json
}
```

The client IDs come from the GitHub repository secrets selected by
`.github/workflows/main_zeroopsai.yml` and
`.github/workflows/main_zeroops-backend.yml`. Do not put client IDs, tenant
credentials, or generated application secrets into this repository.

If a credential named `github-main` already exists, inspect its issuer,
subject, and audience instead of creating a duplicate. The issuer must be
`https://token.actions.githubusercontent.com`, the audience must be
`api://AzureADTokenExchange`, and the subject must match the exact value above.

## Verification

Pushes and manual workflow dispatches to the deployment jobs must retain:

```yaml
if: github.event_name != 'pull_request' && github.ref == 'refs/heads/main'
permissions:
  id-token: write
```

Do not add a GitHub deployment environment to these jobs without first
provisioning a second federated credential whose subject uses
`environment:<environment-name>`. GitHub changes the OIDC subject whenever a
job declares an environment.

The Azure Login step is the authoritative verification. `AADSTS700213` means
the Entra application selected by that job does not have a federated credential
matching the token's exact issuer, subject, and audience.
