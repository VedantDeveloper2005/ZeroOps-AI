# ZeroOps live verification — September 13, 2026

## Verified

- Foundry lists exactly one prompt agent: `zeroops-architecture-advisor`, version 3, running. The user deleted `demo`.
- The live Chrome architecture page returned an advisor recommendation from `gpt-5.6-terra`, version 3, with recorded latency 28.2 seconds. The live plan assistant answered an evidence-grounding question successfully. It explicitly identified unverified runtime and capacity facts.
- The backend code release preceding this verification completed (deployment `2fba6fbb-f204-43c1-9b47-ed14908e0eac`). Its health endpoint reported production and a working database.
- An actual Terraform apply created the Linux B1 plan `asp-zeroops-workloads` and Basic registry `zeroopsapps7abb` in Mohit's existing `zeroops-demo-workload-rg`. This was an operator bootstrap, not application-pipeline execution.
- The existing `VedantDeveloper2005` ZeroOps user is connected to Mohit's subscription `7abbc9d1-585e-452a-9f6d-a137a0015959`, Central India, using those hosting resources. The app's validation function read the actual resources before saving the connection at 04:01:11 UTC. Chrome Settings displays the verified connection.
- The workload identity `zeroops-mohit-workloads` has Contributor only on that resource group. Its client secret is stored in Key Vault, never in source or browser output.
- Connection validation exposed an Azure SDK compatibility bug: `ResourcesOperations.get_by_id` takes keyword-only `api_version`. Both calls were corrected; all seven connector tests passed using the SDK-compatible signature.
- VMSS `vmss-zops-tfexec` reports provisioning state Succeeded and capacity zero. All five execution queues have zero active and zero dead-letter messages.

## Backend SDK repair release

ZIP SHA-256: `4795372c7828e92d83b1eac9320e762f0895207b9070a317cb38c5cfb984c4b6`.
Azure deployment ID: `d720ac27-5039-45e3-8e29-a737f4292d38`.
Azure reports RuntimeSuccessful, one successful instance and no failed instances. Runtime startup completed at 04:09:08 UTC; the production health endpoint reports a working database. Live Chrome Verify & save succeeded after sign-in refresh. A read-only database check confirms connection status connected and a fresh verification timestamp of 2026-09-13 04:11:00.265957 UTC.

## Remaining blockers to a real application release

1. No repository-analysis, Terraform-generation, or history-projector Function apps are deployed in the inspected subscriptions.
2. The app release endpoint writes PostgreSQL deployment jobs. The existing VMSS image consumes immutable Service Bus Terraform envelopes; it does not consume those application release jobs.
3. A Docker `RepositoryCheckExecutor` implementation has now been added and unit-tested; its live integration is still incomplete. The development executor must stay disabled in production; running untrusted repository scripts on the credentialed control plane is not an acceptable substitute.
4. The isolated Function model adapter now supports the retained prompt agent and passed a live connectivity test. The Terraform agent route generates real output; deploying and verifying the full flow remains outstanding.
5. Application managed-identity registry pull permissions still need controlled provisioning. Resource-group Contributor does not grant permission to assign Azure roles.

No application deployment, VMSS Terraform apply, health-check pass, or pipeline completion was fabricated. Foundry chat success and a verified Azure connection do not establish end-to-end release readiness.
