import json
import os
import subprocess
import tempfile
from typing import Generator

try:
    from backend.config import K8S_AVAILABLE
except ImportError:
    from config import K8S_AVAILABLE


def _stream_process(cmd: list[str], cwd: str | None = None) -> Generator[str, None, int]:
    process = subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    while True:
        line = process.stdout.readline() if process.stdout else ""
        if not line and process.poll() is not None:
            break
        if line:
            yield f"  {line.strip()}\n"
    return process.returncode or 0


def extract_project_id(manifests_yaml: str) -> str:
    marker = "namespace: zeroops-"
    if marker in manifests_yaml:
        tail = manifests_yaml.split(marker, 1)[1]
        return tail.splitlines()[0].strip() or "web-app"
    return "web-app"


def apply_manifests(manifests_yaml: str) -> Generator[str, None, None]:
    """Apply Kubernetes manifests to the active cluster context."""
    if not K8S_AVAILABLE:
        message = "Kubernetes context is not available. Configure kubectl before deployment."
        yield f"{message}\n"
        raise RuntimeError(message)

    yield "Deploying manifests to active Kubernetes cluster context...\n"
    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w", encoding="utf-8") as f:
        f.write(manifests_yaml)
        temp_path = f.name

    try:
        cmd = ["kubectl", "apply", "-f", temp_path]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        while True:
            line = process.stdout.readline() if process.stdout else ""
            if not line and process.poll() is not None:
                break
            if line:
                yield f"  {line.strip()}\n"
        if process.returncode != 0:
            raise RuntimeError(f"kubectl apply failed with return code {process.returncode}")
        yield "Kubernetes manifests applied successfully.\n"
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass


def get_pod_logs(pod_name: str) -> Generator[str, None, None]:
    """Stream live logs from a Kubernetes pod."""
    if not K8S_AVAILABLE:
        yield "[ERROR] Kubernetes context is not available. Live pod logs cannot be streamed.\n"
        return

    try:
        process = subprocess.Popen(
            ["kubectl", "logs", "-f", pod_name, "--tail=50"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        while True:
            line = process.stdout.readline() if process.stdout else ""
            if not line:
                break
            yield line
    except Exception as e:
        yield f"[ERROR] Failed to stream Kubernetes pod logs: {e}\n"


def scale_replicas(name: str, replicas: int, namespace: str | None = None) -> bool:
    """Scale deployment replicas in Kubernetes."""
    if not namespace:
        namespace = f"zeroops-{name.replace('-service', '').replace('-svc', '')}"

    if not K8S_AVAILABLE:
        return False

    try:
        res = subprocess.run(
            ["kubectl", "scale", f"deployment/{name}", f"--replicas={replicas}", "-n", namespace],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        return res.returncode == 0
    except Exception:
        return False


def apply_manifests_to_cluster(yaml_content: str, namespace: str | None = None) -> Generator[str, None, None]:
    """Apply arbitrary manifests with kubectl."""
    if not K8S_AVAILABLE:
        message = "Kubernetes context is not available. Cannot apply manifests."
        yield f"  {message}\n"
        raise RuntimeError(message)

    with tempfile.NamedTemporaryFile(suffix=".yaml", delete=False, mode="w", encoding="utf-8") as f:
        f.write(yaml_content)
        temp_path = f.name

    try:
        cmd = ["kubectl", "apply", "-f", temp_path]
        if namespace:
            cmd.extend(["-n", namespace])

        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        while True:
            line = process.stdout.readline() if process.stdout else ""
            if not line and process.poll() is not None:
                break
            if line:
                yield f"  {line.strip()}\n"
        if process.returncode != 0:
            raise RuntimeError(f"kubectl apply failed with return code {process.returncode}")
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass


def setup_namespace(project_id: str) -> Generator[str, None, None]:
    """Set up an isolated namespace for a project."""
    ns_name = f"zeroops-{project_id}"
    namespace_manifest = f"""apiVersion: v1
kind: Namespace
metadata:
  name: {ns_name}
  labels:
    tenant: {project_id}
    security-isolation: "true"
---
apiVersion: v1
kind: ResourceQuota
metadata:
  name: project-quota
  namespace: {ns_name}
spec:
  hard:
    pods: "10"
    requests.cpu: "2"
    requests.memory: "4Gi"
    limits.cpu: "4"
    limits.memory: "8Gi"
---
apiVersion: v1
kind: LimitRange
metadata:
  name: project-limits
  namespace: {ns_name}
spec:
  limits:
  - default:
      cpu: "500m"
      memory: "512Mi"
    defaultRequest:
      cpu: "100m"
      memory: "128Mi"
    type: Container
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: project-admin
  namespace: {ns_name}
rules:
- apiGroups: ["", "apps", "networking.k8s.io", "autoscaling"]
  resources: ["deployments", "services", "pods", "pods/log", "ingresses", "horizontalpodautoscalers", "secrets", "configmaps"]
  verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: project-admin-binding
  namespace: {ns_name}
subjects:
- kind: ServiceAccount
  name: default
  namespace: {ns_name}
roleRef:
  kind: Role
  name: project-admin
  apiGroup: rbac.authorization.k8s.io
"""

    yield f"Preparing deployment isolation namespace {ns_name}...\n"
    for log in apply_manifests_to_cluster(namespace_manifest):
        yield log
    yield "Kubernetes namespace isolation applied successfully.\n"


def sync_secrets_to_namespace(project_id: str, secrets: dict) -> Generator[str, None, None]:
    """Create a Kubernetes Secret object inside the project namespace."""
    ns_name = f"zeroops-{project_id}"

    if not secrets:
        yield f"No active secrets found for zeroops-{project_id}. Skipping secret injection.\n"
        return

    secret_manifest = f"""apiVersion: v1
kind: Secret
metadata:
  name: project-secrets
  namespace: {ns_name}
type: Opaque
stringData:
"""
    for k, v in secrets.items():
        secret_manifest += f"  {k}: \"{v}\"\n"

    yield f"Synchronizing configured secrets to namespace {ns_name}...\n"
    for log in apply_manifests_to_cluster(secret_manifest, ns_name):
        yield log
    yield f"Secrets synchronized to Kubernetes Secret 'project-secrets' in namespace {ns_name}.\n"


def verify_rollout(project_id: str, timeout: str = "120s") -> Generator[str, None, None]:
    """Verify a Kubernetes deployment rollout."""
    if not K8S_AVAILABLE:
        message = "Kubernetes context is not available. Cannot verify rollout."
        yield f"{message}\n"
        raise RuntimeError(message)

    ns_name = f"zeroops-{project_id}"
    yield f"Verifying rollout for deployment/{project_id} in {ns_name}...\n"
    process = subprocess.Popen(
        ["kubectl", "rollout", "status", f"deployment/{project_id}", "-n", ns_name, f"--timeout={timeout}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    while True:
        line = process.stdout.readline() if process.stdout else ""
        if not line and process.poll() is not None:
            break
        if line:
            yield f"  {line.strip()}\n"
    if process.returncode != 0:
        raise RuntimeError(f"Kubernetes rollout verification failed with return code {process.returncode}")
    yield "Kubernetes rollout verified successfully.\n"


def get_hpa_status(project_id: str) -> dict:
    """Fetch Horizontal Pod Autoscaler details for the project."""
    if not K8S_AVAILABLE:
        return {
            "available": False,
            "message": "Kubernetes context is not available.",
            "minReplicas": None,
            "maxReplicas": None,
            "currentReplicas": None,
            "targetCPU": None,
            "currentCPU": None,
            "targetMemory": None,
            "currentMemory": None,
        }

    ns_name = f"zeroops-{project_id}"
    try:
        res = subprocess.run(
            ["kubectl", "get", "hpa", "-n", ns_name, "-o", "json"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=5,
        )
        if res.returncode != 0:
            return {"available": False, "message": res.stderr.strip() or "No HPA found."}

        data = json.loads(res.stdout)
        items = data.get("items", [data]) if isinstance(data, dict) else []
        if not items:
            return {"available": False, "message": "No HPA configured for this project."}

        hpa = items[0]
        spec = hpa.get("spec", {})
        status = hpa.get("status", {})
        target_cpu = None
        current_cpu = None

        for metric in spec.get("metrics", []):
            if metric.get("type") == "Resource" and metric.get("resource", {}).get("name") == "cpu":
                target_cpu = metric.get("resource", {}).get("target", {}).get("averageUtilization")

        for metric in status.get("currentMetrics", []):
            if metric.get("type") == "Resource" and metric.get("resource", {}).get("name") == "cpu":
                current_cpu = metric.get("resource", {}).get("current", {}).get("averageUtilization")

        return {
            "available": True,
            "minReplicas": spec.get("minReplicas"),
            "maxReplicas": spec.get("maxReplicas"),
            "currentReplicas": status.get("currentReplicas"),
            "targetCPU": target_cpu,
            "currentCPU": current_cpu,
            "targetMemory": None,
            "currentMemory": None,
        }
    except Exception as e:
        return {"available": False, "message": f"Error fetching HPA: {e}"}


def get_cluster_resource_metrics(project_id: str | None = None) -> dict:
    """Return Kubernetes cluster metric summaries from kubectl."""
    if not K8S_AVAILABLE:
        return {"available": False, "message": "Kubernetes context is not available."}

    ns_name = f"zeroops-{project_id}" if project_id else None
    pods_total = 0
    pods_healthy = 0
    cpu_val = None
    mem_val = None

    try:
        cmd = ["kubectl", "get", "pods", "--no-headers"]
        if ns_name:
            cmd.extend(["-n", ns_name])
        else:
            cmd.extend(["--all-namespaces"])

        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        if res.returncode == 0:
            lines = [line for line in res.stdout.strip().split("\n") if line.strip()]
            pods_total = len(lines)
            pods_healthy = sum(1 for line in lines if "Running" in line or "Completed" in line)

        res_top = subprocess.run(["kubectl", "top", "nodes"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=5)
        if res_top.returncode == 0:
            node_lines = res_top.stdout.strip().split("\n")[1:]
            if node_lines:
                parts = node_lines[0].split()
                if len(parts) >= 5:
                    cpu_val = float(parts[2].replace("%", ""))
                    mem_val = float(parts[4].replace("%", ""))
    except Exception as e:
        return {"available": False, "message": f"Error querying cluster metrics: {e}"}

    return {
        "available": True,
        "cpu": cpu_val,
        "memory": mem_val,
        "podsHealthy": pods_healthy,
        "podsTotal": pods_total,
        "traffic": None,
        "errorRate": None,
    }
