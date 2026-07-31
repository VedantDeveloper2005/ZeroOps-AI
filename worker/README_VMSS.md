# Hardened Terraform VMSS runner

`worker/vmss_main.py` is the VMSS execution entry point. The previous
PostgreSQL/App Service worker remains in the repository for compatibility, but
the new immutable image starts this Service Bus worker.

## Immutable toolchain

The Docker image pins:

- Azure CLI `2.87.0` on an amd64 MCR image digest.
- Terraform `1.15.8`, verified against HashiCorp's published SHA-256.
- TFLint `0.64.0`, verified against its release checksum.
- Checkov `3.3.8`.
- Exact Azure Identity, Service Bus, and Blob SDK versions.

The image runs as UID 10001, has no Docker socket, drops all Linux
capabilities, enables `no-new-privileges`, mounts only bounded temporary
filesystems, and receives no credentials. Managed identity supplies all Azure
tokens.

## Plan/apply state machine

1. Receive one session-bound Service Bus message in peek-lock mode.
2. Reject unknown fields, raw source/plan content, noncanonical IDs,
   noncanonical tenant-artifact paths, unsafe state keys, or an invalid job
   digest.
3. Protect the exact Flexible VMSS instance from scale-in.
4. Acquire a renewable executor-storage lease for the tenant workspace.
5. Download the immutable source bundle by HTTPS URI, ETag, size, and SHA-256.
6. Extract it without links, path traversal, embedded state/plans/keys, or an
   existing `.terraform` directory.
7. Require `.terraform.lock.hcl`, verify the exact Terraform version, initialize
   the Entra-authenticated backend, then run fmt, validate, TFLint, and Checkov.
8. For `plan`, create a saved binary plan, reduce `terraform show -json` in
   memory to action counts/resource kinds, and store the binary in the
   executor-only container.
9. For `apply`, download the already-saved binary plan and require exact matches
   across plan digest, ETag, plan job digest, bundle digest, and approval
   record. The only apply command supplies the saved plan path.
10. Publish sanitized history, write a completion receipt, settle the queue
    message, release the state lease, and finally release scale-in protection.

Terraform output, Checkov output, provider diagnostics, source values, plan
JSON, state, and plan bytes are never printed or included in workflow events.

## Queue contract

All messages use schema `1.0`. Producers calculate `job_digest` as SHA-256 of
canonical JSON (UTF-8, sorted keys, compact separators) before adding the
`job_digest` field. Tenant, project, user, workflow/run, and job identifiers
are canonical UUIDs. In particular, `project_id` is mandatory so the history
projector never has to infer ownership.

A plan message carries a query-free HTTPS Blob URI in the backend's
content-addressed user-artifact form:

```text
https://<artifact-account>.blob.core.windows.net/
t-<40 lowercase hex>/objects/<artifact UUID>/v<positive integer>/<sha256>
```

The URI has no SAS or other query parameters, and its terminal digest must
equal `bundle.sha256`. The executor uses managed identity and the immutable
ETag in the envelope to download it. Sanitized plan summaries and apply
receipts are written back into the same opaque tenant container using the same
`objects/<artifact>/v1/<sha256>` convention.

An apply message also carries:

- `saved_plan`: executor blob name, ETag, SHA-256, original plan job digest, and
  bundle digest.
- `approval`: immutable approval ID, approving user, UTC timestamp, decision
  `approved`, and the same four plan/bundle identifiers.

Approval expires after 24 hours. Apply messages whose queue, operation, ETag,
digest, tenant prefix, or approval differs are dead-lettered without invoking
Terraform.

The executor returns a `plan_handle` only on its private control result and
persists an allowlisted copy in the executor-only completion receipt so the
trusted orchestration path can construct a later apply request. The
user-history event is a separate `workflow-event.v1` document with UUID
tenant/project/run/correlation fields, `actor_type=vmss`, bounded safe
metadata, and at most a sanitized user-artifact reference. It never contains
that plan handle, executor Blob paths, state keys, ETags, SAS URLs, source
values, or raw tool output. Its deterministic event ID includes the tenant,
run, job, and event type so the Functions history projector can process
retries idempotently.

## Lease and termination behavior

The worker has four independent protections:

- Service Bus peek-lock auto-renewal.
- Service Bus sessions for per-workflow FIFO processing.
- A renewable executor Blob lease keyed by tenant state key.
- Azure VM scale-in protection on the current instance.

Terraform also retains its native AzureRM backend state lock. A five-minute VMSS
termination notification gives the service time to stop accepting work.
Protection is held until the event and completion receipt are durable. If
protection release fails, readiness becomes unhealthy so Azure Monitor can
surface an operator reconciliation requirement rather than silently leaking
compute cost.
