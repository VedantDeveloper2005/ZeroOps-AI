import asyncio
import uuid
import requests
import threading
from typing import Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, BackgroundTasks, Depends, Response
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

try:
    from backend import config
    from backend.services import git, ai, k8s, pipeline, vault
    from backend.database import get_db, init_db, database_available
    from backend import models, schemas, auth
except ImportError:
    import config
    from services import git, ai, k8s, pipeline, vault
    from database import get_db, init_db, database_available
    import models, schemas, auth

app = FastAPI(title="ZeroOps AI MVP Backend")

# Enable CORS for Next.js frontend proxy
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=config.ALLOW_CREDENTIALS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Startup database initialization
@app.on_event("startup")
async def startup_db():
    await init_db()

# Helper to format user response consistently
def map_user_response(user: models.User) -> schemas.UserResponse:
    return schemas.UserResponse(
        id=user.id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        firstName=user.first_name,
        lastName=user.last_name,
        provider=user.provider,
        provider_id=user.provider_id,
        avatar_url=user.avatar_url,
        plan=user.plan,
        created_at=user.created_at.isoformat() if user.created_at else None
    )

# AUTHENTICATION ROUTERS

@app.post("/api/auth/signup", response_model=schemas.UserResponse)
async def signup(req: schemas.UserCreate, response: Response, db: AsyncSession = Depends(get_db)):
    """User signup endpoint."""
    first_name = req.first_name or req.firstName
    last_name = req.last_name or req.lastName
    
    # Check if user already exists
    try:
        result = await db.execute(select(models.User).filter(models.User.email == req.email))
        existing_user = result.scalars().first()
    except Exception as e:
        print(f"Database error during signup search: {e}")
        raise HTTPException(status_code=503, detail="Database is currently unavailable.")
        
    if existing_user:
        raise HTTPException(status_code=400, detail="A user with this email address already exists.")
        
    # Hash password
    password_hash = auth.get_password_hash(req.password)
    
    # Create new user
    new_user = models.User(
        id=uuid.uuid4(),
        first_name=first_name,
        last_name=last_name,
        email=req.email,
        password_hash=password_hash,
        provider="local",
        plan="starter"
    )
    
    try:
        db.add(new_user)
        await db.commit()
        await db.refresh(new_user)
    except Exception as e:
        await db.rollback()
        print(f"Database error during user insertion: {e}")
        raise HTTPException(status_code=500, detail="Failed to register user in database.")
        
    # Generate token
    token = auth.create_access_token(data={"sub": str(new_user.id)})
    
    # Set HTTP-only secure cookie
    is_prod = config.APP_ENV == "production"
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        max_age=config.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=is_prod
    )
    
    return map_user_response(new_user)

@app.post("/api/auth/login", response_model=schemas.UserResponse)
async def login(req: schemas.UserLogin, response: Response, db: AsyncSession = Depends(get_db)):
    """User login endpoint."""
    try:
        result = await db.execute(select(models.User).filter(models.User.email == req.email))
        user = result.scalars().first()
    except Exception as e:
        print(f"Database error during login search: {e}")
        raise HTTPException(status_code=503, detail="Database is currently unavailable.")
        
    if not user or not user.password_hash:
        raise HTTPException(status_code=400, detail="Invalid email or password.")
        
    # Verify password
    if not auth.verify_password(req.password, user.password_hash):
        raise HTTPException(status_code=400, detail="Invalid email or password.")
        
    # Generate token
    token = auth.create_access_token(data={"sub": str(user.id)})
    
    # Set HTTP-only secure cookie
    is_prod = config.APP_ENV == "production"
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        max_age=config.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=is_prod
    )
    
    return map_user_response(user)

@app.get("/api/auth/me", response_model=schemas.UserResponse)
async def get_me(current_user: models.User = Depends(auth.get_current_user)):
    """Get currently logged in user profile details."""
    return map_user_response(current_user)

@app.post("/api/auth/logout")
async def logout(response: Response):
    """Logs the user out by deleting their session cookie."""
    is_prod = config.APP_ENV == "production"
    response.delete_cookie(
        key="session_token",
        samesite="lax",
        secure=is_prod,
        httponly=True
    )
    return {"status": "success", "message": "Logged out successfully."}

class OAuthRequest(BaseModel):
    provider: str
    provider_id: str
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    avatar_url: Optional[str] = None

@app.post("/api/auth/oauth", response_model=schemas.UserResponse)
async def oauth_authenticate(req: OAuthRequest, response: Response, db: AsyncSession = Depends(get_db)):
    """Future-ready OAuth login/registration interface."""
    try:
        # Check by provider + provider_id first
        result = await db.execute(
            select(models.User).filter(
                (models.User.provider == req.provider) & (models.User.provider_id == req.provider_id)
            )
        )
        user = result.scalars().first()
        
        if not user:
            # Check if email is already taken by a local user
            result_email = await db.execute(select(models.User).filter(models.User.email == req.email))
            existing_email = result_email.scalars().first()
            
            if existing_email:
                # Link local account to OAuth
                user = existing_email
                user.provider = req.provider
                user.provider_id = req.provider_id
                if req.avatar_url:
                    user.avatar_url = req.avatar_url
                await db.commit()
                await db.refresh(user)
            else:
                # Create new OAuth profile
                user = models.User(
                    id=uuid.uuid4(),
                    first_name=req.first_name,
                    last_name=req.last_name,
                    email=req.email,
                    password_hash=None, # No password required for OAuth
                    provider=req.provider,
                    provider_id=req.provider_id,
                    avatar_url=req.avatar_url,
                    plan="starter"
                )
                db.add(user)
                await db.commit()
                await db.refresh(user)
    except Exception as e:
        print(f"Database error during OAuth: {e}")
        raise HTTPException(status_code=500, detail="Database failure during authentication.")
        
    # Generate token
    token = auth.create_access_token(data={"sub": str(user.id)})
    
    # Set cookie
    is_prod = config.APP_ENV == "production"
    response.set_cookie(
        key="session_token",
        value=token,
        httponly=True,
        max_age=config.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        samesite="lax",
        secure=is_prod
    )
    
    return map_user_response(user)

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
    res = requests.get("https://api.github.com/user", headers=headers, timeout=10)
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
    res = requests.get("https://api.github.com/user/repos?per_page=100&sort=updated", headers=headers, timeout=10)
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
        analysis = ai.analyze_repository(repo_path, pipeline.normalize_project_id(req.repo))
        return analysis
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/health")
async def api_health():
    return {
        "status": "ok",
        "service": "zeroops-backend",
        "environment": config.APP_ENV,
        "dockerAvailable": config.DOCKER_AVAILABLE,
        "kubernetesAvailable": config.K8S_AVAILABLE,
        "openAIConfigured": bool(config.OPENAI_API_KEY),
    }

@app.get("/healthz")
async def healthz():
    return {"status": "ok"}

@app.get("/api/deployments")
async def get_deployments():
    """Retrieve deployments pipeline history."""
    if not pipeline.deployments_history:
        # Return default mocks initially
        return [
            { "id": "dep-001", "app": "web-app", "repo": "acme/web-app", "environment": "production", "status": "running", "duration": "2m 34s", "deployedBy": "AI Auto-Deploy", "time": "2 min ago", "version": "v2.4.1" },
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
    return [{"key": k, "value": "********"} for k in secrets.keys()]

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
    name = req.projectId
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
    
    stop_stream = threading.Event()
    try:
        loop = asyncio.get_event_loop()

        def stream():
            for log_line in k8s.get_pod_logs(pod_name):
                if stop_stream.is_set():
                    break
                future = asyncio.run_coroutine_threadsafe(websocket.send_text(log_line), loop)
                try:
                    future.result(timeout=10)
                except Exception:
                    break

        await loop.run_in_executor(None, stream)
    except WebSocketDisconnect:
        print(f"Logs connection closed for {pod_name}")
    except Exception as e:
        print(f"Logs WS error in {pod_name}: {e}")
    finally:
        stop_stream.set()
