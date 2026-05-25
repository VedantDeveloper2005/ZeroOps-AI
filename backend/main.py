import asyncio
import uuid
import requests
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from backend import config
from backend.services import git, ai, k8s, pipeline, vault

app = FastAPI(title="ZeroOps AI MVP Backend")

# Enable CORS for Next.js frontend proxy
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory settings state
settings_store = {
    "predictiveScaling": True,
    "autoRollback": True,
    "aiThreatMitigation": True,
    "autoOOMRestart": True,
    "slackNotifications": False,
    "emailAlerts": True,
}

# Active Personal Access Token (PAT) for GitHub
github_pat_store = {"token": config.GITHUB_TOKEN}

class ConnectRequest(BaseModel):
    token: str

class DeployRequest(BaseModel):
    repo: str
    branch: str

class ScaleRequest(BaseModel):
    name: str
    replicas: int

class SecretCreateRequest(BaseModel):
    projectId: str
    key: str
    value: str

class HPAConfigureRequest(BaseModel):
    projectId: str
    minReplicas: int
    maxReplicas: int
    cpuTarget: int

@app.post("/api/github/connect")
async def connect_github(req: ConnectRequest):
    """Authenticate and store Personal Access Token (PAT)"""
    token = req.token.strip()
    if not token:
        raise HTTPException(status_code=400, detail="Token cannot be empty")
        
    # Validate token against GitHub API
    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get("https://api.github.com/user", headers=headers)
    if res.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid GitHub Token")
        
    github_pat_store["token"] = token
    return {"status": "success", "username": res.json().get("login")}

connected_repos = [
    {"id": "repo-001", "name": "web-app", "fullName": "acme/web-app", "framework": "Next.js", "language": "TypeScript", "lastCommit": "2 min ago", "lastCommitMessage": "feat: add dashboard analytics", "lastCommitAuthor": "Vedant S.", "deploymentStatus": "running", "stars": 142, "totalDeployments": 48},
    {"id": "repo-002", "name": "api-gateway", "fullName": "acme/api-gateway", "framework": "Express.js", "language": "TypeScript", "lastCommit": "15 min ago", "lastCommitMessage": "fix: rate limiter config", "lastCommitAuthor": "Sarah K.", "deploymentStatus": "running", "stars": 89, "totalDeployments": 112},
    {"id": "repo-003", "name": "payments", "fullName": "acme/payments", "framework": "FastAPI", "language": "Python", "lastCommit": "1 hour ago", "lastCommitMessage": "chore: update stripe sdk", "lastCommitAuthor": "Alex M.", "deploymentStatus": "stopped", "stars": 67, "totalDeployments": 34},
    {"id": "repo-004", "name": "auth", "fullName": "acme/auth", "framework": "NestJS", "language": "TypeScript", "lastCommit": "3 hours ago", "lastCommitMessage": "feat: add oauth2 pkce flow", "lastCommitAuthor": "Vedant S.", "deploymentStatus": "running", "stars": 56, "totalDeployments": 78},
    {"id": "repo-005", "name": "ml-service", "fullName": "acme/ml-service", "framework": "Flask", "language": "Python", "lastCommit": "1 day ago", "lastCommitMessage": "feat: v2 recommendation engine", "lastCommitAuthor": "Lisa T.", "deploymentStatus": "running", "stars": 203, "totalDeployments": 23}
]

class RepoCreateRequest(BaseModel):
    name: str
    fullName: str
    framework: str
    language: str

@app.get("/api/github/repos")
async def get_github_repos():
    """Fetch user repositories. Falls back to mock data if no token."""
    token = github_pat_store["token"]
    if not token:
        return connected_repos

    headers = {"Authorization": f"Bearer {token}"}
    res = requests.get("https://api.github.com/user/repos?per_page=100&sort=updated", headers=headers)
    if res.status_code != 200:
        return connected_repos
        
    repos = []
    for item in res.json():
        lang = item.get("language") or "TypeScript"
        framework = "Next.js" if lang == "TypeScript" else "FastAPI" if lang == "Python" else "Express.js"
        
        repos.append({
            "id": str(item.get("id")),
            "name": item.get("name"),
            "fullName": item.get("full_name"),
            "framework": framework,
            "language": lang,
            "lastCommit": "Just now",
            "lastCommitMessage": "Branch updates managed by ZeroOps",
            "lastCommitAuthor": item.get("owner", {}).get("login", "Vedant S."),
            "deploymentStatus": "stopped",
            "stars": item.get("stargazers_count", 0),
            "totalDeployments": 0
        })
    return repos

@app.post("/api/github/repos")
async def add_connected_repo(req: RepoCreateRequest):
    """Add a new connected repository to the store."""
    new_repo = {
        "id": f"repo-{uuid.uuid4().hex[:6]}",
        "name": req.name,
        "fullName": req.fullName,
        "framework": req.framework,
        "language": req.language,
        "lastCommit": "Just now",
        "lastCommitMessage": "Initial commit managed by ZeroOps",
        "lastCommitAuthor": "Vedant S.",
        "deploymentStatus": "stopped",
        "stars": 0,
        "totalDeployments": 0
    }
    connected_repos.append(new_repo)
    return new_repo

@app.get("/api/github/repo-metadata")
async def get_repo_metadata(repo: str):
    """List branches for a repo."""
    token = github_pat_store["token"]
    branches = git.get_branches(repo, token)
    return {"branches": branches}

@app.post("/api/ai/analyze")
async def analyze_repo(req: DeployRequest):
    """Clones and scans a repository to generate deployments config."""
    token = github_pat_store["token"]
    try:
        # Clone repo
        repo_path = git.clone_repo(req.repo, token)
        # Perform AI scan
        analysis = ai.analyze_repository(repo_path)
        return analysis
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/deployments")
async def get_deployments():
    """Retrieve deployments pipeline history."""
    if not pipeline.deployments_history:
        # Return default mocks initially
        return [
            { "id": "dep-001", "app": "web-frontend", "repo": "acme/web-app", "environment": "production", "status": "running", "duration": "2m 34s", "deployedBy": "AI Auto-Deploy", "time": "2 min ago", "version": "v2.4.1" },
            { "id": "dep-002", "app": "api-gateway", "repo": "acme/api-gateway", "environment": "production", "status": "running", "duration": "1m 48s", "deployedBy": "Vedant S.", "time": "15 min ago", "version": "v3.1.0" },
            { "id": "dep-005", "app": "notification-svc", "repo": "acme/notifications", "environment": "development", "status": "failed", "duration": "4m 01s", "deployedBy": "Vedant S.", "time": "3 hours ago", "version": "v0.9.2" }
        ]
    return pipeline.deployments_history

@app.post("/api/deployments/deploy")
async def start_deploy(req: DeployRequest, background_tasks: BackgroundTasks):
    """Trigger a new app deployment in the background."""
    deploy_id = f"dep-{uuid.uuid4().hex[:6]}"
    background_tasks.add_task(pipeline.run_deployment_pipeline, deploy_id, req.repo, req.branch)
    return {"status": "success", "deployment_id": deploy_id}

@app.post("/api/deployments/scale")
async def scale_deployment(req: ScaleRequest):
    """Scale a deployment replica set count."""
    success = k8s.scale_replicas(req.name, req.replicas)
    if not success:
         raise HTTPException(status_code=500, detail="Failed to scale replicas")
    return {"status": "success", "replicas": req.replicas}

@app.get("/api/monitoring/metrics")
async def get_metrics(project_id: Optional[str] = None):
    """Fetch live cluster metric nodes and utilization levels."""
    return k8s.get_cluster_resource_metrics(project_id)

@app.post("/api/secrets")
async def add_secret(req: SecretCreateRequest):
    """Add or update a Key Vault secret for a project."""
    success = vault.set_project_secret(req.projectId, req.key, req.value)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to save secret to Key Vault")
    return {"status": "success", "key": req.key}

@app.get("/api/secrets/{project_id}")
async def list_secrets(project_id: str):
    """Retrieve secret keys (hiding values) for a project."""
    secrets = vault.get_project_secrets(project_id)
    return [{"key": k, "value": "••••••••"} for k in secrets.keys()]

@app.delete("/api/secrets/{project_id}/{key}")
async def delete_secret(project_id: str, key: str):
    """Remove a secret from Key Vault."""
    success = vault.delete_project_secret(project_id, key)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete secret from Key Vault")
    return {"status": "success"}

@app.post("/api/autoscaling/configure")
async def configure_autoscaling(req: HPAConfigureRequest):
    """Updates HPA parameters inside the namespace."""
    ns_name = f"zeroops-{req.projectId}"
    name = "web-frontend"
    hpa_manifest = f"""apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: {name}-hpa
  namespace: {ns_name}
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: {name}
  minReplicas: {req.minReplicas}
  maxReplicas: {req.maxReplicas}
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: {req.cpuTarget}
"""
    if k8s.K8S_AVAILABLE:
        try:
            for log in k8s.apply_manifests_to_cluster(hpa_manifest, ns_name):
                print(log.strip())
        except Exception as e:
            print(f"Failed to update cluster HPA: {e}")
    return {"status": "success", "minReplicas": req.minReplicas, "maxReplicas": req.maxReplicas}

@app.get("/api/autoscaling/{project_id}")
async def get_autoscaling_status(project_id: str):
    """Fetch live Horizontal Pod Autoscaling details."""
    return k8s.get_hpa_status(project_id)

@app.get("/api/security/status/{project_id}")
async def get_security_status(project_id: str):
    """Returns compliance and security center metrics for the project space."""
    secrets = vault.get_project_secrets(project_id)
    secrets_count = len(secrets)
    score = 96 if secrets_count > 0 else 92
    vulnerabilities_count = 0 if secrets_count > 0 else 2
    return {
        "securityScore": score,
        "firewallStatus": "Active",
        "httpsStatus": "Active",
        "secretsManaged": secrets_count,
        "vulnerabilities": vulnerabilities_count,
        "soc2Status": "Compliant",
        "threatLevel": "Low",
        "namespaceIsolated": True,
        "rbacEnabled": True
    }

@app.get("/api/settings")
async def get_settings():
    return settings_store

@app.post("/api/settings")
async def update_settings(updates: dict):
    settings_store.update(updates)
    return settings_store

# WEBSOCKET CHANNELS

@app.websocket("/ws/deployments/{deploy_id}")
async def deploy_websocket(websocket: WebSocket, deploy_id: str):
    """Websocket streaming live deployment build updates and pipeline log lines."""
    await websocket.accept()
    await pipeline.register_connection(deploy_id, websocket)
    
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        pipeline.unregister_connection(deploy_id, websocket)
    except Exception as e:
        print(f"WS error in {deploy_id}: {e}")
        pipeline.unregister_connection(deploy_id, websocket)

@app.websocket("/ws/logs/{pod_name}")
async def logs_websocket(websocket: WebSocket, pod_name: str):
    """Websocket streaming real-time kubectl logs from a container pod."""
    await websocket.accept()
    
    # Run async log stream
    try:
        loop = asyncio.get_event_loop()
        # Stream logs in a separate thread so it doesn't block the async loop
        def stream():
            for log_line in k8s.get_pod_logs(pod_name):
                # Send synchronously via run_coroutine_threadsafe
                asyncio.run_coroutine_threadsafe(websocket.send_text(log_line), loop)
                
        # Start thread
        await loop.run_in_executor(None, stream)
    except WebSocketDisconnect:
        print(f"Logs connection closed for {pod_name}")
    except Exception as e:
        print(f"Logs WS error in {pod_name}: {e}")
