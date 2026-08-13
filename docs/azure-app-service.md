# Azure Hosting Guide

ZeroOps is Azure-only. Customers connect a repository or upload a ZIP, then ZeroOps builds the code in Azure Container Registry and releases it to Azure App Service. The customer sees launch progress and the verified public URL; platform implementation details stay in the background.

## Customer application prerequisites

Each connected Azure account needs:

- An existing resource group, Azure Container Registry, and Linux App Service plan. The plan must be in the configured application region; ACR may be in another region, though co-location is recommended.
- A service principal with least-privilege access to that resource group, plus permission to assign the app identity the `AcrPull` role on its registry.
- A ZeroOps Key Vault configured for the control plane. Client credentials are stored only in Key Vault—never in the database or a local fallback file.

The deployment worker uses Azure Container Registry Tasks to build the customer image. It creates or updates an App Service site with a managed identity for image pulls. A deployment becomes `running` only after Azure reports that the site is running and the returned URL responds.

## Control-plane configuration

```text
APP_ENV=production
AZURE_KEYVAULT_URL=https://<zeroops-vault>.vault.azure.net/
```

These are the only bootstrap App Service settings. Enable the app's managed
identity and store `DATABASE_URL`, `JWT_SECRET`, `FRONTEND_URL`,
`CORS_ORIGINS`, OAuth credentials, SMTP/Twilio credentials, and all remaining
application settings directly in Key Vault. See
[production-key-vault.md](production-key-vault.md) for the exact naming
convention. The application fails closed in production if Key Vault or a
required value is unavailable.

The isolated deployment worker must include the Azure CLI. Do not run customer builds in the frontend process or depend on a local Docker daemon.

The repository workflow builds `worker/Dockerfile` into an existing ACR and
updates an existing, private Azure Container App with one minimum replica.
Configure the repository variables documented in
`.github/workflows/main_zeroops-backend.yml`, grant that Container App managed
identity Key Vault access and ACR pull access, and configure its readiness
probe for `/ready` on port `8085`.

ZIP uploads remain available for source review and architecture planning, but
they are not queueable for deployment: their extracted source currently lives
on API-local storage that an isolated worker cannot read. A deployment request
returns a clear conflict response until durable shared source storage is
implemented.

## Before a real Azure rollout

1. Confirm the subscription and region, then validate quotas.
2. Grant the deployment identity only the required resource-group and registry scopes.
3. Verify Key Vault access through the control plane managed identity.
4. Run the local test suite, frontend lint/build, and Azure pre-deployment validation.
5. Publish a test application and verify its Azure-issued address before enabling customer traffic.
