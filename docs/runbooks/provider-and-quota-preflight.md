# Azure Provider and Quota Preflight

Run this preflight after explicit deployment authorization and before a real
Terraform plan. No ZeroOps workload resource was created during local
preparation. However, an earlier validation plan automatically registered 31
subscription resource providers on 2026-07-29; this is a recorded
control-plane side effect, not a workload deployment. The AzureRM provider now
sets `resource_provider_registrations = "none"` to prevent repetition.

## Fixed context

```text
Subscription: 9277603e-b858-4253-b1ed-e6747e316519
Region: centralindia
Resource group: zeroops-rg
```

Confirm these values with the operator at execution time. Never infer a
subscription from an old Terraform state file.

## Provider registration

Verify these providers and register only the ones used by the selected
environment:

```text
Microsoft.Authorization
Microsoft.App
Microsoft.Compute
Microsoft.ContainerRegistry
Microsoft.Insights
Microsoft.KeyVault
Microsoft.ManagedIdentity
Microsoft.Network
Microsoft.ServiceBus
Microsoft.Storage
Microsoft.Web
```

`Microsoft.App` is required by the Flex Consumption subnet delegation
(`Microsoft.App/environments`). `Microsoft.Quota` is required only if the
generic quota API is used for the live check. Provider registration is a
subscription mutation and requires explicit authorization.

Wait for every required provider to reach `Registered`; do not continue while a
provider is `Registering`.

## Quota checks

Check one provider/resource at a time:

1. `Microsoft.Compute` regional total vCPU and D-family quota.
2. Availability of `Standard_D2ads_v5` in Central India zones 1 and 2.
3. Flex Consumption regional memory/core quota for three Function apps.
4. Standard public IP quota for the NAT gateway.
5. PostgreSQL Flexible Server General Purpose vCores.
6. Storage account count in Central India.
7. Service Bus namespace count.
8. ACR usage and regional availability.

The production maximum is ten 2-vCPU VMSS instances, or 20 vCPU. The test
maximum is one instance, or 2 vCPU. If the available quota is below the selected
profile, reduce the profile or obtain a quota increase before planning.

The current subscription blocks the generic quota API because
`Microsoft.Quota` is not registered. If the deployment operator authorizes its
registration, rerun the quota check and replace fallback evidence with live
values. Do not register it merely to satisfy local validation.

## Availability zones

The selected VM SKU is available in Central India. This subscription currently
reports zone 3 as restricted, so production uses zones 1 and 2. Re-query the SKU
at deployment time because subscription restrictions and regional capacity can
change.

## Global names

Recheck every globally unique name derived by `infra/locals.tf` immediately
before plan: the artifact/executor/Function-host Storage Accounts, two model
Key Vaults, Service Bus namespace, ACR, and Function app host names. Use the
selected environment plus `name_suffix` to derive all names; do not copy old
example names or manually change one occurrence.

If a name is unavailable, change only the deterministic suffix input and
regenerate all dependent DNS/settings references. Do not manually change a
single occurrence.

## Existing-resource safety

Before referencing an existing resource:

- compare subscription, resource group, type, and name;
- export the current resource properties;
- verify that the Terraform address is a `data` source, not a managed resource;
- run a refresh-only plan;
- require zero replacement actions for the existing B1 plan, web app, API app,
  PostgreSQL server, Key Vault, and managed identities.

Stop if Terraform proposes creating, replacing, or mutating an existing
control-plane resource. This root has no import steps.

## Cost preflight

- Confirm the environment profile is `test` unless production was explicitly
  approved.
- Confirm VMSS capacity starts at zero.
- Confirm Function always-ready instances are zero.
- Confirm Service Bus Standard and ACR Basic in test.
- Confirm private endpoints/Premium SKUs are enabled only for the production
  requirements that need them.
- Confirm Log Analytics retention, sampling, and daily cap.
- Confirm the Azure budget amount and notification recipients.
- Attach a dated pricing/cost estimate to the plan approval.

## Evidence to retain

Store the following as a preflight artifact:

- Azure account and tenant IDs;
- provider states;
- quota limits, current usage, and available capacity;
- SKU/zone availability output;
- global-name checks;
- existing-resource inventory;
- Terraform/tool versions;
- selected environment profile;
- timestamp and operator identity.

Do not include access tokens, subscription credentials, connection strings, or
Key Vault secret values.
