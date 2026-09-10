# Cross-tenant demo execution plane

This Terraform root is intentionally independent of `infra/`. It deploys only
the Terraform execution plane into subscription `7abbc9d1-585e-452a-9f6d-a137a0015959`:

- a dedicated VMSS, VNet, NSG, NAT egress IP, managed identity, ACR, Service
  Bus queues, and two storage accounts;
- one separate demo workload resource group on which the runner alone receives
  Contributor; and
- optional queue/blob roles for the target-tenant service principal created by
  the existing App Service's cross-tenant managed-identity federation bridge.

The App Service resources in subscription `9277603e-b858-4253-b1ed-e6747e316519`
are neither read nor changed by this root. The runner does not accept raw shell
scripts or free-form Terraform. It accepts only the existing immutable,
validated plan/apply envelope and retains the saved-plan approval gate.

Deployment is staged:

1. Bootstrap a dedicated encrypted Entra-only Terraform state account.
2. Apply with `deploy_runner=false` to create the foundation.
3. Build `worker/Dockerfile` in the new ACR with `--platform linux/amd64`, then retrieve its immutable digest.
4. Apply with `deploy_runner=true`, the digest, and an SSH *public* key.
5. Create the cross-tenant Entra app/FIC, add the target service principal,
   and reapply with its target-tenant principal ID for queue/blob sender RBAC.

The first runner image starts at VMSS capacity zero. Azure Monitor autoscale
raises it to one only for active plan/apply queue messages.
