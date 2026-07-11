# Azure Deployment Plan

> **Status:** Planning — Azure subscription, region, and quota verification are still required before infrastructure deployment.

## Goal

Operate ZeroOps as an Azure-only SaaS. A customer supplies code, approves launch, and receives a real URL only after Azure Container Apps reports a ready revision and the public endpoint is reachable.

## Architecture

| Component | Azure service | Cost / safety choice |
|---|---|---|
| Customer app build | Azure Container Registry Tasks | Cloud builds; no Docker daemon in the control plane |
| Customer app runtime | Azure Container Apps, Consumption | External HTTPS ingress, scale-to-zero, max 2 replicas |
| Private image pull | Managed identity + `AcrPull` | No registry passwords |
| Deployment secrets | Azure Key Vault | No local filesystem fallback |
| Release tracking | Existing PostgreSQL database | A release is `running` only after verified URL and revision |
| Control plane async work | Isolated deployment worker | Customer build/release work never blocks the web request path |

## Product decisions

- Azure Container Apps replaces AKS/GKE as the only customer-hosting target.
- No simulated deployment, fabricated database host, or guessed live URL is allowed.
- Google Cloud endpoints return a retirement response; existing database rows remain untouched for safe migration.
- Automatic source-code mutation is disabled. A user reviews and commits changes in their own repository.
- Customer app secrets must be stored in Azure Key Vault; unavailable Key Vault blocks the operation.

## Required Azure inputs

| Input | Status |
|---|---|
| Subscription ID | Needs user confirmation |
| Region | Needs user confirmation |
| Resource group | Needs user confirmation |
| Container Registry | Needs user confirmation |
| Container Apps environment | Needs user confirmation |
| Key Vault URL and managed-identity RBAC | Needs user confirmation |

## Quota inventory (to validate after subscription and region are supplied)

| Resource type | Planned quantity | Validation method |
|---|---:|---|
| `Microsoft.App/managedEnvironments` | 1 existing/customer environment | Azure quota CLI |
| `Microsoft.App/containerApps` | One per customer app | Azure quota CLI / Resource Graph |
| `Microsoft.ContainerRegistry/registries` | 1 existing/customer registry | Resource Graph + Azure limits |
| `Microsoft.OperationalInsights/workspaces` | 1 per control-plane environment | Resource Graph + Azure limits |
| `Microsoft.KeyVault/vaults` | 1 control-plane vault | Resource Graph + Azure limits |

## Verification completed locally

- [x] Removed GKE target selection from the launch path and customer-facing settings.
- [x] Replaced local Docker/Kubernetes deployment steps with ACR build + Container Apps release logic.
- [x] Removed Key Vault filesystem fallback and mock credential validation.
- [x] Added unit coverage for Azure-only target selection and application-name normalization.
- [x] Documented the required Key Vault secrets, non-secret app settings, and minimum Azure roles.
- [ ] Run Azure quota checks using the confirmed subscription and region.
- [ ] Generate IaC and run the Azure validation workflow.
- [ ] Deploy a non-production Azure environment and verify a real release end-to-end.

## Next required action

Provide the Azure subscription ID and target region. With those, ZeroOps can perform quota validation, create the Azure deployment artifacts, and safely publish the first non-production environment.
