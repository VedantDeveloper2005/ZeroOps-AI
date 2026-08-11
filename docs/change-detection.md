# Change Detection and AI Reuse

ZeroOps uses deterministic repository fingerprints and path classification to
avoid invoking repository AI on every commit. The decision is persisted with
an explanation and can be audited independently of the model.

## Implementation status

- **Implemented and covered by repository tests:** bounded snapshot
  collection, path normalization, SHA-256 fingerprints, Git diff collection,
  change categories, reuse decisions, and durable snapshot/change records.
- **Partially implemented:** path-level Git diffs require a Git checkout and
  an accessible baseline commit. Archive/upload workspaces can still use
  content fingerprints, but may not have a path diff.
- **Not live verified:** no external GitHub/Azure deployment run was performed
  for this change set.

## Inputs and outputs

After source preparation, the worker collects:

- the immutable target commit SHA;
- a bounded representation of repository files;
- environment-variable names, never their values;
- deterministic framework/service facts when available;
- the latest successful repository-analysis snapshot for the project;
- changed Git paths between the previous successful revision and the target,
  when the baseline can be fetched safely.

It writes:

- `RepositoryAnalysisSnapshot`, containing hashes and a bounded content-free
  analysis summary; and
- `ChangeAnalysis`, containing categories, counts, up to 100 sampled paths,
  digests over the complete normalized path set, and the reason AI was or was
  not required.

## Retry history and per-run evidence

Migration `007_change_analysis_retry_history` replaces the old cross-run
uniqueness constraint on tenant, project, target revision, and change
fingerprint with a non-unique lookup index. This permits two distinct pipeline
runs against the same immutable commit and fingerprint, including a fresh
approval-bound run, to retain separate `ChangeAnalysis` decisions.

This does not permit duplicate evidence within one run. The tenant-scoped
idempotency constraint remains enforced, and repeating the same approval
request returns the already-created fresh run instead of manufacturing another
one. Reuse may still reference an earlier safe snapshot; the current run keeps
its own auditable change decision.

## Fingerprints

The snapshot computes separate SHA-256 values for:

- the represented repository;
- dependency files;
- Dockerfiles/Containerfiles;
- infrastructure files;
- Kubernetes manifests;
- important deployment/security configuration; and
- an architecture fingerprint combining those hashes with normalized
  framework, detected-service, and environment-variable-name facts.

The persisted fingerprint never includes raw `.env` content. Environment files
contribute only validated variable names. Files larger than 2 MiB are
represented by a framed SHA-256 marker instead of inline bytes.

Snapshot collection does not follow symlinks and ignores generated/vendor
directories including `.git`, `.next`, `build`, `coverage`, `dist`,
`node_modules`, `target`, and `vendor`.

Current bounds are:

| Bound | Value |
|---|---:|
| Source files | 25,000 |
| Represented content | 128 MiB |
| Inline bytes per file | 2 MiB |
| Persisted sampled changed paths | 100 |
| Detected services | 100 |
| Environment-variable names | 256 |

Exceeding a bound is an evidence failure, not permission to analyze an
unbounded repository.

## Change categories

Each normalized path can produce one or more stable categories:

| Category | Typical evidence | Fresh repository AI? |
|---|---|---|
| `NO_RELEVANT_CHANGE` | Documentation or ignored/generated paths | No, if a prior snapshot exists |
| `APPLICATION_CODE_CHANGE` | Ordinary application source | No, if architecture fingerprints remain stable |
| `DEPENDENCY_CHANGE` | Lockfiles, package manifests, requirements | Yes |
| `DEPLOYMENT_CONFIG_CHANGE` | Docker, environment-name, workflow, or deployment configuration | Yes |
| `INFRASTRUCTURE_CHANGE` | Terraform, Bicep, Pulumi, or other IaC | Yes |
| `KUBERNETES_CHANGE` | Manifests, Helm, Kustomize | Yes |
| `SECURITY_RELEVANT_CHANGE` | Auth/RBAC/policy/security configuration | Yes |
| `MAJOR_ARCHITECTURE_CHANGE` | Compose or architecture-defining files/facts | Yes |

Classification is conservative: a file may be both security relevant and an
application/deployment change.

## AI decision

The decision is deterministic:

1. With no previous successful snapshot, fresh repository analysis is
   required.
2. Any dependency, deployment configuration, infrastructure, Kubernetes,
   security, or major architecture category requires fresh analysis.
3. Documentation-only, no-relevant-change, and ordinary application-code
   changes reuse the previous safe analysis when deployment-specific
   fingerprints remain compatible.

The persisted reason is one of these conceptual outcomes:

- no previous analysis;
- no deployment-relevant change, so the prior analysis was reused; or
- deployment-relevant changes detected, with the triggering categories.

“AI skipped” is therefore evidence-backed reuse, not an assertion that nothing
changed. Security scans, tests, and builds remain independently applicable.

`repository_ai_required` records the decision to enter the repository-analysis
boundary; it is not proof that an external model returned the result.
`repository_ai_used` becomes true only for a validated model response and the
pipeline records that response's actual provider/model provenance. A provider
failure, deterministic fallback, or the production-isolated Function boundary
keeps `ai_used=false`. The active production release worker does not yet
dispatch that separate Function, so this handoff remains partial.

## Git diff safety

The diff helper:

- accepts only canonical 40-character Git commit SHAs;
- operates only inside the managed workspace;
- invokes Git without a shell;
- fetches only the specific baseline commit when necessary;
- passes GitHub authorization through process environment configuration rather
  than a command-line URL; and
- returns a sorted, deduplicated, bounded path set.

If Git metadata is unavailable, the helper returns no path diff. Fingerprint
differences still protect deployment-relevant architecture groups. This
fallback should be visible in stage evidence rather than represented as a
complete Git comparison.

## Data minimization

Raw source, `.env` values, Git credentials, model prompts, and full model
responses are not stored in `ChangeAnalysis`. A reused snapshot contains a
reference to its predecessor and a bounded safe summary. Only allowlisted
deployment facts such as runtime, framework, package manager, build/start
commands, Kubernetes asset names, and resource hints can enter that summary,
after redaction.

The change classifier can decide whether AI is needed; it cannot authorize a
deployment or override scanner/test failures.
