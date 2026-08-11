import base64
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest
import yaml

from backend.services import aks
from backend.services import ai


DEPLOYMENT = """
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  selector:
    matchLabels: {app: api}
  template:
    metadata:
      labels: {app: api}
    spec:
      containers:
        - name: api
          image: old.example/api:old
"""
DIGEST_IMAGE = "registry.example/api@sha256:" + "a" * 64
CLUSTER_USER_CONFIG = b"""apiVersion: v1
kind: Config
clusters:
  - name: existing-cluster
    cluster:
      server: https://existing-cluster.example.azmk8s.io
      certificate-authority-data: Y2E=
contexts:
  - name: existing-cluster
    context:
      cluster: existing-cluster
      user: clusterUser
current-context: existing-cluster
users:
  - name: clusterUser
    user:
      exec:
        command: kubelogin
"""


def _write_test_kubeconfig(_connection, _secret, destination: Path):
    aks._secure_write(destination, aks._tokenized_kubeconfig(CLUSTER_USER_CONFIG, "short-lived-token"))


def _passed_scan(kind, path, **kwargs):
    assert kind == "kubernetes"
    assert kwargs["required"] is True
    assert kwargs["policy"].block_high is True
    assert (Path(path) / "rendered.yaml").is_file()
    return aks.security_scanner.SecurityScanResult(
        kind="kubernetes",
        tool="trivy",
        status="passed",
        required=True,
        blocking=False,
        summary="No findings detected.",
    )


def test_detects_kubernetes_assets_without_treating_all_yaml_as_manifests(tmp_path: Path):
    (tmp_path / "random.yaml").write_text("name: config", encoding="utf-8")
    manifests = tmp_path / "k8s"
    manifests.mkdir()
    (manifests / "deployment.yaml").write_text(DEPLOYMENT, encoding="utf-8")
    chart = tmp_path / "helm" / "api"
    chart.mkdir(parents=True)
    (chart / "Chart.yaml").write_text("apiVersion: v2\nname: api\nversion: 1.0.0\n", encoding="utf-8")

    assets = aks.detect_kubernetes_assets(tmp_path)

    assert assets.manifest_files == ("k8s/deployment.yaml",)
    assert assets.chart_directories == ("helm/api",)


def test_manifest_render_binds_verified_image_and_namespace(tmp_path: Path):
    manifests = tmp_path / "k8s"
    manifests.mkdir()
    path = manifests / "deployment.yaml"
    path.write_text(DEPLOYMENT, encoding="utf-8")

    documents, workloads = aks.validate_and_render_manifests(
        ["k8s/deployment.yaml"],
        repo_path=tmp_path,
        namespace="zeroops-project",
        image_ref="registry.example/api@sha256:" + "a" * 64,
    )

    assert workloads == ("deployment/api",)
    assert documents[0]["metadata"]["namespace"] == "zeroops-project"
    assert documents[0]["spec"]["template"]["spec"]["containers"][0]["image"].endswith("a" * 64)
    assert documents[0]["spec"]["template"]["spec"]["automountServiceAccountToken"] is False
    assert documents[0]["spec"]["template"]["metadata"]["labels"]["zeroops.ai/release"] == "zeroops-project"


@pytest.mark.parametrize(
    "document, message",
    [
        ("apiVersion: v1\nkind: Secret\nmetadata: {name: credentials}\n", "Raw Kubernetes Secret"),
        ("apiVersion: rbac.authorization.k8s.io/v1\nkind: ClusterRole\nmetadata: {name: admin}\n", "Cluster-scoped"),
        (DEPLOYMENT.replace("name: api", "name: api\n  namespace: another", 1), "targets namespace"),
        (DEPLOYMENT.replace("image: old.example/api:old", "image: old.example/api:old\n          securityContext: {privileged: true}"), "privileged"),
        (DEPLOYMENT.replace("containers:", "serviceAccountName: privileged\n      containers:"), "non-default service account"),
        (DEPLOYMENT.replace("containers:", "volumes: [{name: host, hostPath: {path: /}}]\n      containers:"), "host path"),
        (DEPLOYMENT.replace("containers:", "volumes: [{name: projected, projected: {sources: [{secret: {name: credentials}}]}}]\n      containers:"), "projects a Kubernetes Secret"),
        (DEPLOYMENT.replace("image: old.example/api:old", "image: old.example/api:old\n          envFrom: [{secretRef: {name: credentials}}]"), "references a Kubernetes Secret"),
        (DEPLOYMENT.replace("image: old.example/api:old", "image: old.example/api:old\n          env: [{name: API_KEY, value: plaintext}]"), "embeds a secret-looking"),
        (DEPLOYMENT.replace("containers:", "initContainers: [{name: init, image: attacker.example/init:latest}]\n      containers:"), "init or ephemeral"),
        ("apiVersion: v1\nkind: ConfigMap\nmetadata: {name: settings}\ndata: {password: plaintext}\n", "secret-looking key"),
    ],
)
def test_manifest_policy_fails_closed(tmp_path: Path, document: str, message: str):
    path = tmp_path / "deployment.yaml"
    path.write_text(document, encoding="utf-8")

    with pytest.raises(aks.AksDeploymentError, match=message):
        aks.validate_and_render_manifests(
            [path],
            repo_path=tmp_path,
            namespace="zeroops-project",
            image_ref=DIGEST_IMAGE,
        )


def test_missing_aks_tool_blocks_before_credentials_are_requested(tmp_path: Path, monkeypatch):
    manifests = tmp_path / "k8s"
    manifests.mkdir()
    (manifests / "deployment.yaml").write_text(DEPLOYMENT, encoding="utf-8")
    monkeypatch.setattr(aks.shutil, "which", lambda _name: None)

    with pytest.raises(aks.AksDeploymentError, match="kubectl is unavailable"):
        aks.deploy_existing_cluster(
                connection=type("Connection", (), {
                    "aks_cluster_name": "existing-cluster",
                    "acr_login_server": "registry.example",
                })(),
            client_secret="secret",
            repo_path=tmp_path,
            namespace="zeroops-project",
            image_ref=DIGEST_IMAGE,
            release_name="api",
            kubeconfig_writer=lambda *_: pytest.fail("credentials should not be requested"),
        )


def test_mutable_or_foreign_registry_image_blocks_before_credentials(tmp_path: Path):
    manifests = tmp_path / "k8s"
    manifests.mkdir()
    (manifests / "deployment.yaml").write_text(DEPLOYMENT, encoding="utf-8")
    connection = SimpleNamespace(
        aks_cluster_name="existing-cluster",
        acr_login_server="registry.example",
    )

    with pytest.raises(aks.AksDeploymentError, match="immutable sha256"):
        aks.deploy_existing_cluster(
            connection=connection,
            client_secret="secret",
            repo_path=tmp_path,
            namespace="zeroops-project",
            image_ref="registry.example/api:v1",
            release_name="api",
            kubeconfig_writer=lambda *_: pytest.fail("credentials should not be requested"),
        )
    with pytest.raises(aks.AksDeploymentError, match="connected Azure Container Registry"):
        aks.deploy_existing_cluster(
            connection=connection,
            client_secret="secret",
            repo_path=tmp_path,
            namespace="zeroops-project",
            image_ref="attacker.example/api@sha256:" + "b" * 64,
            release_name="api",
            kubeconfig_writer=lambda *_: pytest.fail("credentials should not be requested"),
        )


def test_kubeconfig_decoder_accepts_only_cluster_user_yaml():
    content = CLUSTER_USER_CONFIG

    assert aks._decode_kubeconfig(base64.b64encode(content)) == content
    with pytest.raises(aks.AksDeploymentError, match="invalid"):
        aks._decode_kubeconfig(base64.b64encode(b"not a kubeconfig"))


def test_tokenized_kubeconfig_removes_exec_and_certificate_credentials():
    rendered = yaml.safe_load(aks._tokenized_kubeconfig(CLUSTER_USER_CONFIG, "short-lived-token"))

    assert rendered["users"] == [{"name": "zeroops-deployer", "user": {"token": "short-lived-token"}}]
    assert "exec" not in str(rendered)
    assert "client-certificate" not in str(rendered)
    assert rendered["clusters"][0]["cluster"]["server"].startswith("https://")


def test_isolated_kubeconfig_rejects_exec_authentication(tmp_path: Path):
    path = tmp_path / "kubeconfig"
    path.write_bytes(CLUSTER_USER_CONFIG)
    path.chmod(0o600)

    with pytest.raises(aks.AksDeploymentError, match="short-lived Entra token"):
        aks._validate_isolated_kubeconfig(path)


def test_cluster_user_writer_never_requests_admin_credentials(tmp_path: Path, monkeypatch):
    calls = []

    class Credential:
        def __init__(self, **kwargs):
            calls.append(("credential", kwargs))

        def get_token(self, scope):
            calls.append(("token", scope))
            return SimpleNamespace(token="short-lived-token")

        def close(self):
            calls.append(("credential-close",))

    class ManagedClusters:
        def list_cluster_user_credentials(self, resource_group, cluster, **kwargs):
            calls.append(("cluster-user", resource_group, cluster, kwargs))
            return SimpleNamespace(kubeconfigs=[SimpleNamespace(value=base64.b64encode(CLUSTER_USER_CONFIG))])

        def __getattr__(self, name):
            if "admin" in name:
                pytest.fail("admin credentials must never be requested")
            raise AttributeError(name)

    class Client:
        def __init__(self, credential, subscription_id):
            calls.append(("client", subscription_id))
            self.managed_clusters = ManagedClusters()

        def close(self):
            calls.append(("client-close",))

    monkeypatch.setattr(aks, "ClientSecretCredential", Credential)
    monkeypatch.setattr(aks, "ContainerServiceClient", Client)
    connection = SimpleNamespace(
        tenant_id="tenant",
        client_id="client",
        subscription_id="subscription",
        resource_group="resource-group",
        aks_cluster_name="existing-cluster",
    )
    destination = tmp_path / "kubeconfig"

    aks._write_cluster_user_kubeconfig(connection, "client-secret", destination)

    configuration = yaml.safe_load(destination.read_text(encoding="utf-8"))
    assert configuration["users"][0]["user"] == {"token": "short-lived-token"}
    assert any(call[0] == "cluster-user" and call[3] == {"format": "exec"} for call in calls)
    assert ("token", aks._AKS_AAD_SCOPE) in calls
    assert ("credential-close",) in calls
    assert ("client-close",) in calls


def test_helm_output_is_validated_from_isolated_render_directory(tmp_path: Path):
    chart = tmp_path / "helm" / "api"
    chart.mkdir(parents=True)
    (chart / "Chart.yaml").write_text("apiVersion: v2\nname: api\nversion: 1.0.0\n", encoding="utf-8")
    temp = tmp_path / "temp"
    temp.mkdir()

    def runner(command, cwd, env, timeout):
        output = Path(command[command.index("--output-dir") + 1]) / "api" / "templates"
        output.mkdir(parents=True)
        (output / "deployment.yaml").write_text(DEPLOYMENT, encoding="utf-8")
        return aks.CommandResult(0, "", "")

    files, validation_root = aks._render_assets(
        root=tmp_path,
        assets=aks.KubernetesAssets(chart_directories=("helm/api",)),
        temp=temp,
        namespace="zeroops-project",
        release_name="api",
        runner=runner,
        environment={},
        kubectl="/tools/kubectl",
        helm="/tools/helm",
    )
    documents, workloads = aks.validate_and_render_manifests(
        files,
        repo_path=validation_root,
        namespace="zeroops-project",
        image_ref=DIGEST_IMAGE,
        release_name="api",
    )

    assert workloads == ("deployment/api",)
    assert documents[0]["metadata"]["namespace"] == "zeroops-project"


def test_kustomize_is_rendered_without_plugins_or_network(tmp_path: Path):
    source = tmp_path / "k8s"
    source.mkdir()
    (source / "kustomization.yaml").write_text("resources: [deployment.yaml]\n", encoding="utf-8")
    (source / "deployment.yaml").write_text(DEPLOYMENT, encoding="utf-8")
    temp = tmp_path / "temp"
    temp.mkdir()

    def runner(command, cwd, env, timeout):
        assert "--enable-alpha-plugins=false" in command
        assert "--network=false" in command
        output = Path(command[command.index("--output") + 1])
        output.write_text(DEPLOYMENT, encoding="utf-8")
        return aks.CommandResult(0, "", "")

    assets = aks.detect_kubernetes_assets(tmp_path)
    assert assets.manifest_files == ()
    files, validation_root = aks._render_assets(
        root=tmp_path,
        assets=assets,
        temp=temp,
        namespace="zeroops-project",
        release_name="api",
        runner=runner,
        environment={},
        kubectl="/tools/kubectl",
        helm=None,
    )

    assert files == [temp / "kustomize-rendered.yaml"]
    assert validation_root == temp


def test_full_rollout_uses_isolated_context_and_returns_real_health(tmp_path: Path, monkeypatch):
    manifests = tmp_path / "k8s"
    manifests.mkdir()
    (manifests / "deployment.yaml").write_text(DEPLOYMENT, encoding="utf-8")
    monkeypatch.setattr(aks.shutil, "which", lambda name: f"/tools/{name}")
    monkeypatch.setenv("KUBECONFIG", "global-kubeconfig")
    monkeypatch.setenv("AZURE_CLIENT_SECRET", "must-not-reach-tools")
    calls = []
    rendered_documents = []

    def runner(command, cwd, env, timeout):
        command = list(command)
        calls.append(command)
        assert env["KUBECONFIG"] != "global-kubeconfig"
        assert "AZURE_CLIENT_SECRET" not in env
        assert all("admin" not in item.lower() for item in command)
        if command[1:3] == ["get", "namespace"]:
            return aks.CommandResult(0, "", "")
        if command[1:3] == ["create", "-f"]:
            namespace = json.loads(Path(command[3]).read_text(encoding="utf-8"))
            assert namespace["metadata"]["labels"]["zeroops.ai/release"] == "api"
            return aks.CommandResult(0, "", "")
        if command[1] == "apply":
            rendered_documents[:] = list(yaml.safe_load_all(Path(command[-1]).read_text(encoding="utf-8")))
            return aks.CommandResult(0, "", "")
        if command[1:3] == ["rollout", "status"]:
            return aks.CommandResult(0, "deployment successfully rolled out", "")
        if command[1:3] == ["get", "deployment/api"]:
            return aks.CommandResult(0, json.dumps({
                "apiVersion": "apps/v1",
                "kind": "Deployment",
                "metadata": {"name": "api", "uid": "deployment-uid", "generation": 3},
                "spec": {"replicas": 1},
                "status": {
                    "observedGeneration": 3,
                    "readyReplicas": 1,
                    "updatedReplicas": 1,
                    "availableReplicas": 1,
                    "unavailableReplicas": 0,
                },
            }), "")
        if command[1:3] == ["get", "service,ingress"]:
            return aks.CommandResult(0, json.dumps({"items": [{
                "kind": "Service",
                "metadata": {"labels": {"zeroops.ai/release": "api"}},
                "spec": {"ports": [{"port": 443, "name": "https"}]},
                "status": {"loadBalancer": {"ingress": [{"ip": "203.0.113.10"}]}},
            }]}), "")
        if command[1:3] == ["get", "pods"]:
            assert command[command.index("--selector") + 1] == "zeroops.ai/release=api"
            return aks.CommandResult(0, json.dumps({"items": [{
                "metadata": {"name": "api-pod", "uid": "pod-uid", "labels": {"zeroops.ai/release": "api"}},
                "status": {
                    "phase": "Running",
                    "conditions": [{"type": "Ready", "status": "True"}],
                    "containerStatuses": [{"ready": True, "restartCount": 2}],
                },
            }]}), "")
        return aks.CommandResult(0, "", "")

    release = aks.deploy_existing_cluster(
        connection=SimpleNamespace(
            aks_cluster_name="existing-cluster",
            acr_login_server="registry.example",
        ),
        client_secret="client-secret",
        repo_path=tmp_path,
        namespace="zeroops-project",
        image_ref=DIGEST_IMAGE,
        release_name="api",
        runner=runner,
        kubeconfig_writer=_write_test_kubeconfig,
        scanner=_passed_scan,
    )

    assert release.rollout_status == "healthy"
    assert release.service_endpoint == "https://203.0.113.10"
    assert release.pod_status == {
        "total": 1,
        "ready": 1,
        "not_ready": 0,
        "pending": 0,
        "failed": 0,
        "succeeded": 0,
        "terminating": 0,
        "restarts": 2,
    }
    assert release.workload_status["deployment/api"]["observed_generation"] == 3
    assert release.deployment_revision.startswith("aks-")
    assert rendered_documents[0]["kind"] == "Deployment"
    assert all(document["kind"] != "Secret" for document in rendered_documents)
    namespace_create = next(index for index, command in enumerate(calls) if command[1:3] == ["create", "-f"])
    dry_run = next(index for index, command in enumerate(calls) if "--dry-run=server" in command)
    assert namespace_create < dry_run
    assert all("--namespace" in command for command in calls if command[1] in {"apply", "rollout"})


def test_existing_unowned_namespace_blocks_before_apply(tmp_path: Path, monkeypatch):
    manifests = tmp_path / "k8s"
    manifests.mkdir()
    (manifests / "deployment.yaml").write_text(DEPLOYMENT, encoding="utf-8")
    monkeypatch.setattr(aks.shutil, "which", lambda name: f"/tools/{name}")

    def runner(command, cwd, env, timeout):
        if list(command)[1:3] == ["get", "namespace"]:
            return aks.CommandResult(0, json.dumps({
                "kind": "Namespace",
                "metadata": {"name": "zeroops-project", "labels": {}},
            }), "")
        return aks.CommandResult(0, "", "")

    with pytest.raises(aks.AksDeploymentError, match="not exclusively owned"):
        aks.deploy_existing_cluster(
            connection=SimpleNamespace(
                aks_cluster_name="existing-cluster",
                acr_login_server="registry.example",
            ),
            client_secret="client-secret",
            repo_path=tmp_path,
            namespace="zeroops-project",
            image_ref=DIGEST_IMAGE,
            release_name="api",
            runner=runner,
            kubeconfig_writer=_write_test_kubeconfig,
            scanner=_passed_scan,
        )


def test_health_metadata_rejects_stale_rollout_and_scopes_pods_to_release():
    with pytest.raises(aks.AksDeploymentError, match="incomplete"):
        aks._workload_health("deployment/api", {
            "kind": "Deployment",
            "metadata": {"name": "api", "uid": "uid", "generation": 2},
            "spec": {"replicas": 1},
            "status": {
                "observedGeneration": 1,
                "readyReplicas": 1,
                "updatedReplicas": 1,
                "availableReplicas": 1,
            },
        })

    counts = aks._pod_counts({"items": [
        {
            "metadata": {"name": "other", "uid": "other", "labels": {"zeroops.ai/release": "other"}},
            "status": {"phase": "Failed"},
        },
        {
            "metadata": {"name": "api", "uid": "api", "labels": {"zeroops.ai/release": "api"}},
            "status": {"phase": "Pending", "containerStatuses": [{"ready": False, "restartCount": 0}]},
        },
    ]}, release_name="api")

    assert counts["total"] == 1
    assert counts["pending"] == 1
    assert counts["not_ready"] == 1
    assert counts["failed"] == 0


def test_repository_scanner_reports_existing_kubernetes_configuration(tmp_path: Path):
    (tmp_path / "package.json").write_text(
        '{"scripts":{"build":"next build","start":"next start"},"dependencies":{"next":"16.2.12"}}',
        encoding="utf-8",
    )
    manifests = tmp_path / "k8s"
    manifests.mkdir()
    (manifests / "deployment.yaml").write_text(DEPLOYMENT, encoding="utf-8")

    result = ai.analyze_repo_local(tmp_path)

    assert result["kubernetes_detected"] is True
    assert result["deployment_strategy"] == "azure-aks"
    assert result["kubernetes_assets"]["manifest_files"] == ["k8s/deployment.yaml"]
