# Existing-Cluster AKS Deployment

ZeroOps can target an existing Azure Kubernetes Service cluster when the
repository contains deterministic Kubernetes evidence and the connected Azure
account supplies the existing-cluster metadata. This is an application-release
adapter, not an AKS provisioning or administration system.

## Implementation status

- **Adapter-implemented and covered by repository tests:** target eligibility,
  manifest/Helm/Kustomize discovery, strict rendering policy, immutable image
  binding, kubeconform and Trivy gates, isolated Entra cluster-user
  credentials, server-side dry-run/apply, rollout checks, bounded endpoint
  metadata inspection, and pod-health evidence.
- **Partially implemented:** deployment depends on a worker image containing
  all tools, the service principal having the exact Azure/Kubernetes
  permissions, and the container build producing a resolvable immutable image
  digest. Control-plane workload identity/managed-identity authentication is
  not implemented; the adapter currently derives a short-lived Entra token
  from the connected service principal. Project environment-variable injection
  is also unavailable. Monitoring collection after rollout is not connected
  automatically. External Service/Ingress verification is not implemented.
  The active pipeline therefore stops at application deployment before calling
  the cluster adapter; it does not knowingly mutate a cluster and then fail at
  a later smoke stage.
- **Not implemented:** AKS cluster creation, node-pool changes, cluster
  upgrades, cluster-wide RBAC/policy installation, Key Vault CSI installation,
  or arbitrary multi-tenant chart deployment.
- **Not live verified:** the available Azure CLI session required interactive
  MFA for AKS discovery. No cluster was accessed and no manifest was applied.

## Target selection

App Service remains the active target for ordinary managed-web workloads. The
target-status API includes AKS but marks it not ready while external
verification is unavailable. Automatic selection blocks a Kubernetes-evidenced
workload instead of silently moving it to App Service. After that blocker is
resolved, `azure-aks` selection still requires both conditions below:

1. deterministic repository evidence identifies Kubernetes manifests, a Helm
   chart, or Kustomize configuration; and
2. the active Azure connection has all AKS prerequisites.

An explicit AKS request currently fails with the external-verification blocker;
without Kubernetes evidence it also fails the evidence gate. A model-provided
deployment suggestion alone is never sufficient evidence.

The shared Azure connection must contain:

- tenant ID;
- subscription ID;
- client/application ID;
- service-principal secret in project/account Key Vault, never the database;
- resource group;
- ACR login server;
- existing AKS cluster name; and
- optionally, a stable namespace prefix.

AKS does not require the App Service plan field. App Service remains eligible
independently when its own prerequisites are configured.

## Worker prerequisites

The deployed worker must provide:

- Python packages `azure-identity`, `azure-mgmt-containerservice`, and
  `PyYAML`;
- `kubectl`;
- `kubeconform`;
- `trivy`; and
- `helm` when a Helm chart is the selected source type.

Any required missing tool blocks the release. The adapter does not download an
unreviewed binary at runtime.

`worker/Dockerfile` remains the separate VMSS Terraform executor.
`worker/Dockerfile.pipeline` is the application-release image and pins
checksum-verified kubectl, kubeconform, Trivy, Helm, and the other pipeline
tools. Platform CI builds that image and checks the installed commands. The
local Docker daemon was unavailable, so the image was not built or run on this
development host; AKS tests still use controlled command results and do not
prove a deployed worker or live cluster is ready.

The Azure identity needs permission to request cluster-user credentials for
the named cluster. The resulting Entra identity must have narrowly scoped
Kubernetes authorization to inspect/create the ZeroOps-owned namespace and
manage only the allowed resource kinds in that namespace. Granting
cluster-admin is neither required nor accepted as the adapter credential path.

## Accepted source shape

Discovery ignores generated/vendor directories and recognizes:

- YAML manifests under `k8s/`, `kubernetes/`, or `manifests/`, plus conventional
  deployment/service/ingress filenames;
- a directory containing `Chart.yaml`; or
- `kustomization.yaml` / `kustomization.yml`.

Automatic deployment requires exactly one unambiguous source type:

- direct manifests; or
- one Helm chart; or
- one Kustomize root.

Multiple charts, mixed source types, ambiguous Kustomize roots, symlinked
source, YAML anchors/aliases, more than 200 manifest files, more than 500 YAML
documents, or more than 2 MiB of manifest input are blocked.

## Manifest policy

Allowed namespace-scoped application kinds are:

```text
ConfigMap
DaemonSet
Deployment
HorizontalPodAutoscaler
Ingress
NetworkPolicy
PodDisruptionBudget
Service
StatefulSet
```

The repository cannot submit `Namespace`, `Secret`, `ServiceAccount`, Role or
RoleBinding resources, cluster roles/bindings, CRDs, nodes, or persistent
volumes. Unknown kinds are blocked rather than passed through.

Each workload must:

- remain in the generated ZeroOps namespace;
- contain exactly one application container for deterministic image binding;
- use the immutable ACR image selected by ZeroOps in the form
  `registry/repository@sha256:<64 lowercase hex>`;
- avoid privileged mode, root execution requests, privilege escalation,
  added Linux capabilities, unconfined seccomp, and Windows host processes;
- avoid host network/PID/IPC, host ports, and hostPath volumes;
- avoid init/ephemeral containers and non-default service accounts in
  automatic mode;
- disable automatic service-account token mounting; and
- avoid Kubernetes Secret references, image-pull secrets, secret volumes, and
  projected service-account tokens.

Use an independently installed and authorized Azure Key Vault CSI design for
runtime secrets. ZeroOps does not install that driver and does not accept a raw
Secret manifest as a substitute. The allowlist also cannot deploy custom
resources such as `SecretProviderClass`, so the CSI driver and any required
class must be pre-provisioned by a cluster operator. Do not place secret values
in ConfigMaps.

The AKS adapter cannot translate ZeroOps project environment variables into
that pre-provisioned CSI design. After the external-verification blocker is
resolved, any configured project environment variables would still fail closed
with `AKS_ENVIRONMENT_INJECTION_UNAVAILABLE`; the adapter never silently omits
them.
Applications selected for AKS must therefore be self-contained or use an
operator-prepared runtime configuration path outside the current ZeroOps
environment-variable feature until a safe binding contract is implemented.

## Credential isolation

For one deployment, the adapter:

1. authenticates to Azure with `ClientSecretCredential` using the stored
   connection identity;
2. calls the AKS cluster-user credential API, never the admin credential API;
3. obtains a short-lived Entra token for the AKS audience;
4. reduces the returned kubeconfig to one TLS-verified cluster, one context,
   and a token-only user;
5. writes it with owner-only permissions in a temporary deployment directory;
6. sets an isolated `KUBECONFIG`, Azure CLI directory, home, and Helm cache;
   and
7. removes the directory when deployment finishes.

Kubeconfigs with an insecure server, embedded exec/auth-provider behavior,
proxy, missing certificate authority, multiple contexts/users, or broad file
permissions are rejected.

## Adapter sequence

The adapter is designed and unit-tested for the following sequence, but the
active pipeline currently blocks before step 1 because it cannot yet complete
the required external verification contract:

1. Detect exactly one supported Kubernetes source type.
2. Render Helm or Kustomize locally when applicable.
3. Parse and enforce the manifest policy.
4. replace the workload container image with the verified immutable digest and
   add ZeroOps ownership labels/selectors;
5. run `kubeconform -strict`;
6. run Trivy Kubernetes configuration scanning with critical and high findings
   blocking;
7. obtain the isolated cluster-user kubeconfig;
8. inspect or create the release-owned namespace;
9. run a strict server-side `kubectl apply --dry-run=server`;
10. run server-side apply using field manager `zeroops`;
11. wait up to ten minutes for each Deployment, StatefulSet, or DaemonSet
    rollout;
12. query workload generations/replicas, services/ingresses, and labeled pods;
13. fail if rollout metadata is incomplete or any expected pod is unready or
    failed; and
14. persist bounded release metadata: cluster, namespace, workload names,
    digest, revision hash, unverified reported endpoint metadata, rollout state,
    and pod counts.

An ingress/load-balancer endpoint may not exist immediately or at all, and the
adapter never invents one. However, the runtime cannot safely discover that
fact only after mutation when it already knows no accepted external verifier
exists. It therefore records `AKS_EXTERNAL_VERIFICATION_UNAVAILABLE` before
server-side apply. A redirect-safe, DNS-safe Azure-aware verifier (or an
explicitly approved internal-only workload contract) must land before the
runtime may invoke the adapter.

## App Service preservation

The AKS adapter does not replace `backend/services/app_service.py`. Automatic
selection continues to prefer the existing Linux App Service plan only when
deterministic Kubernetes evidence is absent. When that evidence is present,
the current AKS readiness blocker is reported instead of silently deploying a
Kubernetes workload to App Service. Legacy Container Apps aliases are routed
to the managed App Service path rather than silently enabling a third target.

The active App Service path builds and scans an immutable ACR image. The AKS
adapter accepts the same immutable-image contract, but current target
readiness stops AKS before image build or cluster mutation. Verification is
target-specific: a successful App Service health check is not evidence of AKS
readiness, and an AKS unit test is not evidence of a live cluster rollout.

## Before enabling in an Azure environment

1. Build and publish `worker/Dockerfile.pipeline`, then verify its pinned
   `kubectl`, `kubeconform`, Trivy, and Helm commands in the target registry.
2. Confirm the repository image can be resolved to an ACR digest, not only a
   mutable tag.
3. Review Azure and Kubernetes RBAC for the exact cluster and namespace
   boundary.
4. Confirm Key Vault and ACR access without printing credentials.
5. Implement and test the public endpoint verifier or a bounded internal-only
   workload contract, then enable the adapter call in the runtime.
6. Run validation-only behavior against a disposable namespace.
7. Perform an authorized release to a non-production cluster and retain the
   redacted evidence.
8. Verify rollout, endpoint, pod, restart, and subsequent telemetry behavior.

Until those checks succeed, describe AKS as code-implemented and locally
tested, not production-verified.
