# Azure Hosting Guide

ZeroOps is Azure-only. Customers connect a repository or upload a ZIP, then ZeroOps builds the code in Azure Container Registry and releases it to Azure Container Apps. The customer sees launch progress and the verified public URL; platform implementation details stay in the background.

## Customer application prerequisites

Each connected Azure account needs:

- An existing resource group, Azure Container Registry, and Container Apps environment in the same region.
- A service principal with least-privilege access to that resource group, plus permission to assign the app identity the `AcrPull` role on its registry.
- A ZeroOps Key Vault configured for the control plane. Client credentials are stored only in Key Vault—never in the database or a local fallback file.

The deployment worker uses Azure Container Registry Tasks to build the customer image. It creates or updates a Container App with external HTTPS ingress, scale-to-zero, a two-replica limit, and a managed identity for image pulls. A deployment becomes `running` only after Azure reports a ready revision and the returned URL responds.

## Control-plane configuration

```text
APP_ENV=production
DATABASE_URL=<managed-postgresql-url>
JWT_SECRET=<long-random-secret>
FRONTEND_URL=https://<zeroops-web-host>
CORS_ORIGINS=https://<zeroops-web-host>
AZURE_KEYVAULT_URL=https://<zeroops-vault>.vault.azure.net/
```

The isolated deployment worker must include the Azure CLI and its `containerapp` extension. Do not run customer builds in the frontend process or depend on a local Docker daemon.

## Before a real Azure rollout

1. Confirm the subscription and region, then validate quotas.
2. Grant the deployment identity only the required resource-group and registry scopes.
3. Verify Key Vault access through the control plane managed identity.
4. Run the local test suite, frontend lint/build, and Azure pre-deployment validation.
5. Publish a test application and verify its Azure-issued address before enabling customer traffic.
