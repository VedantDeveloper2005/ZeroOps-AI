# Secretless deployment bootstrap

This bootstrap resolves Terraform's state-backend chicken-and-egg problem
without creating a client secret or giving the temporary validation VM write
access.

1. An authorized subscription operator runs `bootstrap-state.ps1` once. The
   script verifies the exact tenant/subscription and required provider
   registrations, then creates a separate LRS state account with shared-key
   access disabled, private containers, versioning, soft delete, and a two-day
   lifecycle for saved deployment plans. It never registers a provider.
2. The operator copies both `*.example` files to ignored/local equivalents,
   sets `ARM_USE_CLI=true`, initializes this directory against the new backend,
   reviews a saved plan, and applies it.
3. This root creates separate plan and apply UAMIs. The plan identity has
   Reader on `zeroops-rg`; the apply identity has Contributor plus Role Based
   Access Control Administrator on that resource group only. Both receive Blob
   Data Contributor only on the state and saved-plan containers.
   Before the runner stage, rerun this bootstrap with the dedicated customer
   resource-group ID: the plan identity receives Reader and the apply identity
   receives RBAC Administrator on that one scope so it can bind the executor's
   Contributor role. Neither deployment identity receives workload Contributor
   there.
4. The plan credential trusts only the `main` branch. The apply credential
   trusts only the protected `azure-test-apply` GitHub environment. Configure a
   required reviewer on that environment before any mutation workflow is run.

The IDs in `terraform output -json github_configuration` are configuration,
not credentials. Store them as GitHub variables/secrets only because the
workflow input syntax expects those locations; no client secret exists.
