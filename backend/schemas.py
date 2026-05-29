from pydantic import BaseModel, EmailStr, Field
from typing import Optional, List, Any
from datetime import datetime
import uuid


# ──────────────────────────────────────────────
# AUTH SCHEMAS
# ──────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=6)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    firstName: Optional[str] = None
    lastName: Optional[str] = None

class UserLogin(BaseModel):
    email: EmailStr
    password: str

class UserResponse(BaseModel):
    id: uuid.UUID
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    provider: str
    provider_id: Optional[str] = None
    avatar_url: Optional[str] = None
    plan: str
    created_at: Optional[str] = None
    github_connected: bool = False
    github_username: Optional[str] = None

    class Config:
        orm_mode = True
        from_attributes = True


# ──────────────────────────────────────────────
# PROJECT SCHEMAS
# ──────────────────────────────────────────────

class ProjectCreate(BaseModel):
    name: str
    full_name: str
    repo_url: Optional[str] = None
    framework: str = "Next.js"
    language: str = "TypeScript"
    branch: str = "main"
    region: str = "eastus"

class ProjectResponse(BaseModel):
    id: uuid.UUID
    name: str
    full_name: str
    repo_url: Optional[str] = None
    framework: str
    language: str
    branch: str
    region: str
    status: str
    last_deployed_at: Optional[str] = None
    created_at: Optional[str] = None
    deployment_count: int = 0
    latest_deployment_status: Optional[str] = None

    class Config:
        from_attributes = True


# ──────────────────────────────────────────────
# DEPLOYMENT SCHEMAS
# ──────────────────────────────────────────────

class DeploymentCreate(BaseModel):
    project_id: uuid.UUID
    branch: str = "main"
    environment: str = "production"

class DeploymentResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    project_name: Optional[str] = None
    status: str
    environment: str
    branch: str
    version: Optional[str] = None
    commit_sha: Optional[str] = None
    image: Optional[str] = None
    duration_seconds: Optional[int] = None
    duration: Optional[str] = None  # Human-readable: "2m 34s"
    live_url: Optional[str] = None
    deployed_by: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None

    class Config:
        from_attributes = True

class DeploymentLogResponse(BaseModel):
    line_number: int
    level: str
    message: str
    timestamp: Optional[str] = None

    class Config:
        from_attributes = True

class DeploymentDetailResponse(DeploymentResponse):
    logs: List[DeploymentLogResponse] = []


# ──────────────────────────────────────────────
# NOTIFICATION SCHEMAS
# ──────────────────────────────────────────────

class NotificationResponse(BaseModel):
    id: uuid.UUID
    title: str
    message: str
    type: str
    category: str
    read: bool
    action_url: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


# ──────────────────────────────────────────────
# AI ACTION SCHEMAS
# ──────────────────────────────────────────────

class AIActionResponse(BaseModel):
    id: uuid.UUID
    project_id: Optional[uuid.UUID] = None
    type: str
    severity: str
    message: str
    recommendation: Optional[str] = None
    status: str
    icon: str
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


# ──────────────────────────────────────────────
# AI ANALYSIS SCHEMAS
# ──────────────────────────────────────────────

class AIAnalysisResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    framework: Optional[str] = None
    framework_version: Optional[str] = None
    language: Optional[str] = None
    risk_score: int = 0
    confidence: int = 0
    cpu_recommendation: Optional[str] = None
    memory_recommendation: Optional[str] = None
    storage_recommendation: Optional[str] = None
    port: Optional[str] = None
    dependencies: List[str] = []
    vulnerabilities: List[str] = []
    dockerfile: Optional[str] = None
    kubernetes_manifest: Optional[str] = None
    created_at: Optional[str] = None

    class Config:
        from_attributes = True


# ──────────────────────────────────────────────
# DASHBOARD SCHEMAS
# ──────────────────────────────────────────────

class DashboardStats(BaseModel):
    total_projects: int = 0
    total_deployments: int = 0
    active_deployments: int = 0
    failed_deployments: int = 0
    security_score: int = 0
    pending_ai_actions: int = 0
    unread_notifications: int = 0
    has_deployed: bool = False


# ──────────────────────────────────────────────
# USER SETTINGS SCHEMAS
# ──────────────────────────────────────────────

class UserSettingsResponse(BaseModel):
    predictive_scaling: bool = True
    auto_rollback: bool = True
    ai_threat_mitigation: bool = True
    auto_oom_restart: bool = True
    slack_notifications: bool = False
    email_alerts: bool = True
    theme: str = "dark"

    class Config:
        from_attributes = True

class UserSettingsUpdate(BaseModel):
    predictive_scaling: Optional[bool] = None
    auto_rollback: Optional[bool] = None
    ai_threat_mitigation: Optional[bool] = None
    auto_oom_restart: Optional[bool] = None
    slack_notifications: Optional[bool] = None
    email_alerts: Optional[bool] = None
    theme: Optional[str] = None


# ──────────────────────────────────────────────
# USER PROFILE SCHEMAS
# ──────────────────────────────────────────────

class UserProfileResponse(BaseModel):
    id: uuid.UUID
    email: str
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    avatar_url: Optional[str] = None
    plan: str
    provider: str
    created_at: Optional[str] = None
    total_projects: int = 0
    total_deployments: int = 0
    active_deployments: int = 0

    class Config:
        from_attributes = True

class UserProfileUpdate(BaseModel):
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    avatar_url: Optional[str] = None


# ──────────────────────────────────────────────
# LEGACY COMPATIBILITY
# ──────────────────────────────────────────────

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

class OAuthRequest(BaseModel):
    provider: str
    provider_id: str
    email: EmailStr
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    avatar_url: Optional[str] = None


# ──────────────────────────────────────────────
# GITHUB OAUTH SCHEMAS
# ──────────────────────────────────────────────

class GitHubRepoResponse(BaseModel):
    id: int
    name: str
    full_name: str
    description: Optional[str] = None
    private: bool = False
    language: Optional[str] = None
    stargazers_count: int = 0
    default_branch: str = "main"
    updated_at: str = ""
    html_url: str = ""
    owner_avatar_url: Optional[str] = None

class GitHubStatusResponse(BaseModel):
    connected: bool = False
    username: Optional[str] = None
    avatar_url: Optional[str] = None

class GitHubReposListResponse(BaseModel):
    repos: List[GitHubRepoResponse] = []
    total_count: int = 0
    page: int = 1
    per_page: int = 30
    has_next: bool = False


# ──────────────────────────────────────────────
# ENVIRONMENT VARIABLES & TELEMETRY SCHEMAS
# ──────────────────────────────────────────────

class EnvVarResponse(BaseModel):
    id: uuid.UUID
    key: str
    value: str
    is_secret: bool
    created_at: Optional[str] = None

    class Config:
        from_attributes = True

class EnvVarCreate(BaseModel):
    key: str
    value: str
    is_secret: bool = False

class TelemetryMetricResponse(BaseModel):
    cpu: List[dict] = []
    memory: List[dict] = []
    uptime: str = "99.99%"
    error_rate: str = "0.0%"
    response_time: str = "45ms"
    request_count: int = 1200
