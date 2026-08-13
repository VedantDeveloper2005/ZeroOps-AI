# Terraform Execution Runbook

## Scope

This runbook defines the intended production path from a generated Terraform
bundle to an Azure apply. It applies to both human operations and automation.
Any shortcut around these gates is a security incident.

**Current implementation status:** Phase 0 is enforced as plan-only in both the
runner entry point and Terraform. The VMSS reads only the plan queue, autoscale
watches only that queue, its workload-scope role is Reader, and neither the
backend nor executor identity has apply-queue RBAC. The `terraform-apply` queue
is retained as an unbound reserved contract name; no application identity can
send to it or receive from it. Apply message contracts and executor code remain
dormant for future work. The authenticated API's durable approval issuance,
single-use atomic consumption, scope/cost-envelope binding, and end-to-end
apply producer are not yet complete. Apply must remain disabled until those
items are implemented and verified in a disposable workload scope.

## Preconditions

- The operation has an internal tenant, project, run, and approved architecture
  revision.
- The Terraform bundle is immutable and has a server-computed SHA-256 digest.
- No secret value is present in the bundle or queue message.
- The runner image is referenced by immutable registry digest.
- The VMSS managed identity has only the target-specific roles approved for the
  run.
- Remote state uses Entra authentication, Blob leases, versioning, soft delete,
  and an environment-specific key.

## Plan job

1. Receive an ID-only `TerraformPlanJobV1` message.
2. Validate message schema and reject unknown fields.
3. Load the run and verify tenant/project ownership.
4. Download the bundle by versioned Blob URI.
5. Verify its length and SHA-256 digest before extraction.
6. Extract into a fresh job directory. Reject symlinks, device files, absolute
   paths, and `..` traversal.
7. Verify every file and Terraform resource against the approved manifest.
8. Run:

   ```text
   terraform fmt -check -recursive
   terraform init -backend=false
   terraform validate
   tflint --recursive
   checkov -d .
   terraform init with the approved backend configuration
   terraform plan -out=plan.tfplan
   terraform show -json plan.tfplan
   ```

9. Run deterministic policy and cost checks against the plan JSON.
10. Store raw `plan.tfplan` in executor-only storage.
11. Store sanitized plan JSON, policy evidence, cost evidence, tool versions,
    and digests in tenant artifact storage.
12. Emit `terraform.plan.completed` or a redacted failure event.
13. Request human approval for the exact plan digest.

The plan job never calls `terraform apply`.

## Required production approval record

The production approval record must be immutable after decision and include:

- approval ID and single-use nonce;
- tenant, project, and run IDs;
- architecture revision and digest;
- bundle digest and raw saved-plan digest;
- backend state key;
- target subscription and resource group;
- verified cost estimate and configured maximum;
- policy result digest;
- requester and approver identities;
- creation, decision, and expiry timestamps.

A changed bundle, changed target, changed state key, changed price evidence, or
new plan must produce a different approval request. The current worker only
verifies the exact job/plan/bundle binding it is given; it cannot itself prove
that the control plane atomically consumed a user approval.

## Required future production apply job

This section is a design requirement, not a currently reachable runtime path.
Enabling it requires a separately reviewed change that restores the minimum
queue RBAC and workload mutation role only after all controls below exist.

1. The authenticated control plane creates an ID-only `TerraformApplyJobV1`
   message only after atomically consuming the approval nonce.
2. Atomically claim the job and approval nonce.
3. Verify the approval is approved, unused, unexpired, and belongs to the same
   tenant/project/run.
4. Verify the current target, state key, bundle digest, policy digest, cost
   envelope, and raw-plan digest match the approval.
5. Protect the executing VMSS instance from scale-in.
6. Acquire the state Blob lease.
7. Download the raw saved plan by immutable version and verify SHA-256.
8. Run only:

   ```text
   terraform apply -auto-approve plan.tfplan
   ```

9. Run post-deployment health and ownership checks.
10. Persist safe outputs and evidence; never persist secret output values in
    PostgreSQL or telemetry.
11. Mark the approval nonce consumed.
12. Release the Blob lease and scale-in protection in a `finally` path.
13. Emit completion or failure events.

The apply job never runs `terraform plan`, accepts `.tf` changes, or evaluates
model output. No current API route may bypass this flow or enqueue a free-form
apply request.

## Failure handling

| Failure | Required response |
|---|---|
| Digest mismatch | Reject, quarantine artifact, emit security event |
| Approval mismatch/expiry | Reject without retry |
| Policy or cost threshold failure | Return to architecture review |
| State lease unavailable | Retry with bounded backoff; never force unlock automatically |
| VM interruption before apply | Safe retry after lease expiry and job ownership check |
| VM interruption during apply | Mark unknown, inspect state and Azure activity before any retry |
| Terraform partial failure | Preserve checkpoint/evidence, require human review |
| Post-deploy health failure | Execute only an explicitly approved rollback plan |

`terraform force-unlock`, state editing, imports, and taint operations are
privileged break-glass actions. They require a separate audited operator
procedure and are never model-generated or automatically executed.

## Redaction

Before logs or plan JSON enter user-accessible storage:

- remove values marked sensitive;
- remove provider/environment credentials;
- remove access tokens, connection strings, passwords, private keys, and SAS
  signatures;
- replace suspicious high-entropy values with stable redaction tokens;
- retain paths, resource addresses, change actions, safe IDs, hashes, and
  validation evidence.

Raw plans and state are not sanitized in place. They stay in executor-only
storage and are never exposed through the history API.

## Operational verification

For every release of the runner:

- build and scan the image;
- pin Terraform, TFLint, Checkov, Azure CLI, and provider lock-file versions;
- publish by immutable image digest;
- run negative tests for path traversal, secret defaults, provisioners,
  unapproved resources, public endpoints, and stale approvals;
- run a plan-only test against a disposable resource group;
- run an approved apply and destroy against a disposable resource group only
  after explicit Azure deployment authorization.
