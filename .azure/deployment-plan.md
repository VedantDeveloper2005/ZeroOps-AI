# Azure Deployment Plan

> **Status:** Deferred — no Azure resources will be created until the owner explicitly requests deployment.

## Goal

Run ZeroOps as an Azure-only SaaS. When a customer later launches a project, ZeroOps deploys that customer application to Azure App Service and records a live URL only after Azure reports the site running and the public endpoint responds.

## Selected architecture

| Component | Azure service | Decision |
|---|---|---|
| Customer application runtime | Linux Azure App Service | One managed web app per customer project; simple operations and standard HTTPS endpoint |
| Customer application build | Azure Container Registry Tasks | Build customer source remotely; no Docker daemon in the ZeroOps control plane |
| App image access | System-assigned managed identity + `AcrPull` | No registry passwords in the database or UI |
| App secrets | Azure Key Vault + App Service settings | Secret values remain out of the application database and product responses |
| Release tracking | Existing PostgreSQL database | A release is `running` only after an Azure-reported site and endpoint reachability check |
| Control-plane async work | Isolated deployment worker | Customer builds/releases never block a web request |

## Product decisions

- Azure App Service is the sole supported future hosting target for customer applications.
- Azure infrastructure, model/provider choices, registry details, and deployment-worker internals are not shown to customers.
- No simulated deployment, fabricated database host, generated cost, or guessed live URL is allowed.
- Automatic source-code mutation and automatic database provisioning are disabled.
- Customer app secrets must be stored in Azure Key Vault; unavailable Key Vault blocks deployment.

## Required customer Azure connection (only when deployment is enabled)

| Input | Purpose |
|---|---|
| Tenant ID, subscription ID, client ID, client secret | Short-lived authenticated deployment worker session |
| Resource group and region | Ownership and placement of the customer application |
| Existing Linux App Service plan | Capacity tier selected by the account owner |
| Container Registry login server | Remote build and private image source |
| Optional application-name prefix | Stable, readable customer application names |

## Before the first deployment

- Confirm the subscription and target region with the owner.
- Validate provider registration, App Service plan availability, registry access, Key Vault access, and RBAC.
- Run the Azure validation workflow, then deploy a non-production customer project and verify the resulting public URL.

## Current verification

- [x] Azure CLI authenticated to an enabled subscription.
- [x] Azure deployment is intentionally deferred; no resource was created or modified.
- [ ] Complete App Service deployment-path implementation and local verification.
- [ ] Confirm Azure subscription, region, and user-selected App Service plan before any deployment.
- [ ] Run Azure quota/readiness checks and the Azure validation workflow.
- [ ] Perform the first non-production end-to-end release only with explicit owner approval.
