# Azure Deployment Plan — ZeroOps AI

> **Status:** Planning

Generated: 2026-07-26

---

## 1. Project Overview

**Goal:** Make the existing ZeroOps AI website safely deploy from GitHub on every push to `main`, then complete the missing production configuration needed for a real release.

**Path:** Add Components to an existing Azure deployment (MODIFY).

**Repository:** `https://github.com/VedantDeveloper2005/ZeroOps-AI.git`

The existing GitHub Actions workflows already target the two App Service applications. This plan replaces no application identity and uses a new, dedicated deployment identity for GitHub Actions.

---

## 2. Requirements

| Attribute | Value |
|-----------|-------|
| Classification | Production-style SaaS MVP / demonstration |
| Scale | Small (single region) |
| Budget | Cost-optimized; reuse the existing Basic B1 Linux App Service plan |
| Compliance | No additional requirement supplied; secrets remain in Azure Key Vault and must not enter GitHub or source control |
| **Subscription** | Proposed current: Azure for Students (`9277603e-b858-4253-b1ed-e6747e316519`) — requires user confirmation before execution |
| **Location** | Proposed current: Central India (`centralindia`) — requires user confirmation before execution |

### Policy Constraints

The subscription’s enforced **Allowed resource deployment regions** policy permits `centralindia` (as well as Austria East, Indonesia Central, Korea Central, and East Asia). All resources in this plan remain in Central India.

---

## 3. Components Detected

| Component | Type | Technology | Path |
|-----------|------|------------|------|
| web | SSR frontend | Next.js 16 / Node.js 22 | `.` |
| api | API | FastAPI / Python 3.11 | `backend` |
| worker | Background worker | Python, database-backed queue | `worker` |
| database | Relational data | PostgreSQL required by API and worker | Azure resource currently absent |

Existing Azure resources are the `zeroopsai` frontend App Service, the `zeroops-backend` API App Service, a shared Linux Basic B1 App Service plan, `zeroops-kv-prod` Key Vault, and two application user-assigned identities. There is no worker host and the former PostgreSQL server was deleted.

---

## 4. Recipe Selection

**Selected:** AZCLI + existing GitHub Actions

**Rationale:** The applications, App Service plan, Key Vault, and deployment workflows already exist. The immediate work is secure identity, configuration, and validation—not a new infrastructure build. AZCLI is the least disruptive way to configure the existing estate; GitHub Actions remains the delivery mechanism.

---

## 5. Architecture

**Stack:** App Service

### Service Mapping

| Component | Azure Service | SKU / Configuration |
|-----------|---------------|---------------------|
| web | Existing App Service `zeroopsai` | Linux Node 22 on shared Basic B1 plan |
| api | Existing App Service `zeroops-backend` | Linux Python 3.11 on shared Basic B1 plan |
| worker | No host currently | Must be provisioned or intentionally deferred before worker-backed features are live |
| database | PostgreSQL Flexible Server | Must be recreated before API or worker can be production-ready |
| CI/CD identity | New user-assigned managed identity `zeroops-github-deploy-mi` | GitHub Actions OIDC only; Website Contributor at each app scope |

### Supporting Services

| Service | Purpose |
|---------|---------|
| Azure Key Vault `zeroops-kv-prod` | Stores runtime secrets; no secret values are placed in GitHub |
| User-assigned managed identities | Application-to-Key-Vault access; the CI/CD identity is separate and has no Key Vault permission |
| GitHub Actions | Builds and deploys `main` to the existing web apps through Azure OIDC |
| Application Insights / Log Analytics | Not currently found; recommended before public release, but not created in this first CI/CD configuration step |

### Security Design

1. Create exactly one dedicated `zeroops-github-deploy-mi` identity in Central India.
2. Create an OIDC federation restricted to `repo:VedantDeveloper2005/ZeroOps-AI:ref:refs/heads/main` and audience `api://AzureADTokenExchange`.
3. Grant that identity `Website Contributor` only on the two individual App Service resources—not on the resource group, subscription, Key Vault, or database.
4. Preserve the existing workflows’ generic GitHub secret references. The repository administrator must set `AZURE_CLIENT_ID`, `AZURE_TENANT_ID`, and `AZURE_SUBSCRIPTION_ID` in GitHub Actions after the identity is created. OIDC requires no client secret.
5. Set the GitHub Actions repository variable `NEXT_PUBLIC_API_BASE_URL=https://zeroops-backend.azurewebsites.net` for the frontend build.

### Release Readiness Dependencies

Automatic deployment can be configured first, but a genuine production release must wait for all of the following:

- A new managed PostgreSQL database and its encrypted `DATABASE_URL` value in Key Vault. The current database resource does not exist.
- A long, cryptographically random `JWT_SECRET` in Key Vault.
- Real SMTP credentials (or an explicitly approved product decision to remove/disable email flows); they cannot be safely invented.
- `FRONTEND_URL`, `ALLOWED_HOSTS`, and database TLS settings in Key Vault.
- A decision for phone verification: valid Twilio credentials or an explicit configuration disabling it.
- A worker hosting choice, because the current worker has no Azure host.
- HTTPS-only, startup configuration, and health validation for both App Services.

Do not enable Key Vault purge protection in this work item: it is irreversible and needs separate explicit approval.

---

## 6. Provisioning Limit Checklist

### Phase 1: Resource Inventory

| Resource Type | Number to Deploy | Total After Deployment | Limit/Quota | Notes |
|---------------|------------------|------------------------|-------------|-------|
| `Microsoft.ManagedIdentity/userAssignedIdentities` | 1 | 3 in Central India | Quota API does not support this provider; Azure documents an Entra object quota and a creation throttle of 80 identities per subscription/region per 20 seconds | Resource Graph counted 2 existing identities; creating 1 is within the documented throttle. Source: `az quota` fallback + [Azure subscription service limits](https://learn.microsoft.com/en-us/azure/azure-resource-manager/management/azure-subscription-service-limits). |

**Status:** ✅ Capacity is sufficient for the one planned CI/CD identity. No compute, network, database, or monitoring resource is included in the first CI/CD configuration change.

---

## 7. Execution Checklist

### Phase 1: Planning

- [x] Analyze workspace and existing Azure estate
- [x] Gather available requirements and document assumptions
- [ ] Confirm subscription and location with user
- [x] Prepare resource inventory
- [x] Check quota API and validate capacity using Azure Resource Graph plus official service-limit fallback
- [x] Scan codebase and confirm no Copilot SDK routing requirement
- [x] Select AZCLI + GitHub Actions recipe
- [x] Plan architecture and least-privilege access
- [ ] **User approved this plan**

### Phase 2: Execution — after approval only

- [ ] Research App Service deployment and OIDC role requirements from official Microsoft documentation
- [ ] Create the dedicated CI/CD managed identity and its branch-restricted OIDC federation
- [ ] Assign least-privilege deployment access to only `zeroopsai` and `zeroops-backend`
- [ ] Validate the existing GitHub Actions workflows without overwriting unrelated user changes
- [ ] Record the exact GitHub Actions secret/variable values for the repository administrator to enter
- [ ] Apply safe App Service configuration hardening after confirming each cost/security impact
- [ ] Document missing Key Vault values and database/worker production blockers
- [ ] Perform local build and test verification
- [ ] Update this plan status to `Ready for Validation`

### Phase 3: Validation

- [ ] Invoke `azure-validate`
- [ ] Verify workflow OIDC configuration, RBAC scopes, environment configuration, and readiness blockers
- [ ] Update plan status to `Validated`

### Phase 4: Deployment

- [ ] Invoke `azure-deploy` only after validation and the runtime prerequisites are fulfilled
- [ ] Trigger or allow the first GitHub push deployment
- [ ] Verify public endpoint health and application flows after warm-up
- [ ] Update plan status to `Deployed`

---

## 8. Files to Generate or Update

| File | Purpose | Status |
|------|---------|--------|
| `.azure/deployment-plan.md` | Deployment source of truth | ✅ Updated |
| `.github/workflows/main_zeroops-backend.yml` | Existing backend CI/CD workflow | Review only; it has user changes to preserve |
| `.github/workflows/main_zeroopsai.yml` | Existing frontend CI/CD workflow | Review only; it has user changes to preserve |
| `azure.yaml` / `infra/` | Not required for this targeted existing-App-Service configuration | Not planned |

---

## 9. Next Steps

**Current phase:** Awaiting approval.

1. Confirm the Azure subscription and Central India location shown above.
2. Approve creation of the dedicated GitHub deployment identity and its two least-privilege role assignments.
3. Configure the three GitHub Actions OIDC values and frontend API URL in the GitHub repository.
4. Supply real production email credentials and approve a new PostgreSQL deployment before a live backend release.
