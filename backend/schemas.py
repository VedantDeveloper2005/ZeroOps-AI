import re

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator
from typing import Optional, List, Any
from datetime import datetime
import uuid


# ──────────────────────────────────────────────
# AUTH SCHEMAS
# ──────────────────────────────────────────────

class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=12, max_length=128)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    firstName: Optional[str] = None
    lastName: Optional[str] = None
    phone_number: Optional[str] = Field(default=None, max_length=32)
    phoneNumber: Optional[str] = Field(default=None, max_length=32)

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, password: str) -> str:
        if not any(character.islower() for character in password):
            raise ValueError("Password must include a lowercase letter.")
        if not any(character.isupper() for character in password):
            raise ValueError("Password must include an uppercase letter.")
        if not any(character.isdigit() for character in password):
            raise ValueError("Password must include a number.")
        if not any(not character.isalnum() for character in password):
            raise ValueError("Password must include a symbol.")
        return password

    @field_validator("phone_number", "phoneNumber")
    @classmethod
    def validate_phone_number(cls, phone_number: Optional[str]) -> Optional[str]:
        if phone_number in (None, ""):
            return None
        normalized = re.sub(r"[\s().-]", "", phone_number)
        if not re.fullmatch(r"\+[1-9]\d{7,14}", normalized):
            raise ValueError("Enter a valid phone number in international format, for example +14155552671.")
        return normalized

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
    mfa_enabled: bool = False
    mfa_method: str = "totp"
    email_verified: bool = False
    phone_verified: bool = False

    model_config = ConfigDict(from_attributes=True)


class MFAChallengeResponse(BaseModel):
    mfa_required: bool = True
    mfa_method: str = "totp"


class EmailVerificationPending(BaseModel):
    email_verification_required: bool = True
    email: str


class PhoneVerificationPending(BaseModel):
    phone_verification_required: bool = True
    phone_hint: str


class EmailVerificationComplete(BaseModel):
    email_verified: bool = True


class PhoneVerificationComplete(BaseModel):
    phone_verified: bool = True
    authenticated: bool = False


class EmailVerificationRequest(BaseModel):
    email: EmailStr
    token: str


class ResendVerificationRequest(BaseModel):
    email: EmailStr


class MFAMethodRequest(BaseModel):
    method: str = Field(..., pattern=r"^(totp|email)$")



class MFACodeRequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=16)

    @field_validator("code")
    @classmethod
    def validate_code(cls, code: str) -> str:
        normalized = code.strip()
        if not normalized:
            raise ValueError("Enter your authenticator or recovery code.")
        return normalized


class MFASetupResponse(BaseModel):
    manual_key: str
    otpauth_uri: str
    qr_code_data_uri: str
    expires_at: datetime


class MFASetupConfirmResponse(BaseModel):
    recovery_codes: List[str]


class MFAStatusResponse(BaseModel):
    enabled: bool
    method: str = "totp"
    recovery_codes_remaining: int


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


class AzureConnectRequest(BaseModel):
    """Onboarding request for BYOS Azure connection.
    The client_secret is forwarded to Key Vault and NEVER stored in the DB."""
    tenant_id: str
    client_id: str
    client_secret: str
    subscription_id: str
    resource_group: str
    region: str = "eastus"
    acr_login_server: Optional[str] = None
    app_service_plan: Optional[str] = None
    namespace_prefix: Optional[str] = None


class AzureConnectResponse(BaseModel):
    """Response after connecting Azure – never includes the secret."""
    connected: bool
    connection_status: str
    subscription_id: str
    tenant_id: str
    client_id: str
    resource_group: str
    region: str
    acr_login_server: Optional[str] = None
    app_service_plan: Optional[str] = None
    namespace_prefix: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class AzureConnectionUpsert(BaseModel):
    """Azure-only hosting connection settings. Client secrets are never returned."""
    tenant_id: str
    subscription_id: str
    client_id: Optional[str] = None
    client_secret: Optional[str] = None
    region: str = "eastus"
    resource_group: Optional[str] = None
    acr_login_server: Optional[str] = None
    app_service_plan: Optional[str] = None
    namespace_prefix: Optional[str] = None


class AuditLogResponse(BaseModel):
    id: uuid.UUID
    agent_name: str
    action_type: str
    parameters: dict = {}
    risk_tier: str
    approval_status: str
    result_status: str
    result_detail: Optional[str] = None
    created_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class PendingApprovalResponse(BaseModel):
    id: uuid.UUID
    audit_log_id: uuid.UUID
    action_type: str
    parameters: dict = {}
    risk_tier: str
    status: str
    created_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class ApprovalDecisionRequest(BaseModel):
    decision: str = Field(..., pattern="^(approved|denied)$")


class GkeConnectionUpsert(BaseModel):
    gcp_project_id: str
    service_account_email: Optional[str] = None
    service_account_json: Optional[str] = None
    location: str = "us-central1"
    cluster_name: Optional[str] = None
    artifact_registry_host: Optional[str] = None
    artifact_registry_repository: Optional[str] = None
    namespace_prefix: Optional[str] = None


class BillingOperationCreate(BaseModel):
    operation_type: str
    project_id: Optional[uuid.UUID] = None
    deployment_id: Optional[uuid.UUID] = None
    description: Optional[str] = None

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

    model_config = ConfigDict(from_attributes=True)


# ──────────────────────────────────────────────
# DEPLOYMENT SCHEMAS
# ──────────────────────────────────────────────

class DeploymentCreate(BaseModel):
    project_id: uuid.UUID
    branch: str = "main"
    environment: str = "production"
    target_provider: str = "auto"

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
    infrastructure_metadata: Optional[Any] = None

    model_config = ConfigDict(from_attributes=True)

class DeploymentLogResponse(BaseModel):
    line_number: int
    level: str
    message: str
    timestamp: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)

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

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)


# ──────────────────────────────────────────────
# AI ANALYSIS SCHEMAS
# ──────────────────────────────────────────────

class AIAnalysisResponse(BaseModel):
    id: uuid.UUID
    project_id: Optional[uuid.UUID] = None
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
    
    # New AI analysis fields
    runtime: Optional[str] = None
    package_manager: Optional[str] = None
    docker_support: bool = False
    monorepo_structure: Optional[str] = None
    database_dependencies: List[str] = []
    deployment_strategy: Optional[str] = None
    build_commands: Optional[str] = None
    start_commands: Optional[str] = None
    environment_variables: List[str] = []
    explanation: Optional[str] = None
    recommended_compute_tier: Optional[str] = None
    estimated_cost: Optional[str] = None
    recommended_region: Optional[str] = None
    expected_traffic: Optional[str] = None
    
    # Cost & vars detailed metadata
    compute_cost: Optional[float] = None
    database_cost: Optional[float] = None
    platform_fee: Optional[float] = None
    bandwidth_cost: Optional[float] = None
    monitoring_cost: Optional[float] = None
    total_cost: Optional[float] = None
    projected_growth_cost: Optional[float] = None
    why_this_plan: Optional[str] = None
    detected_vars_detail: Optional[List[Any]] = None

    model_config = ConfigDict(from_attributes=True)


class ChatRequest(BaseModel):
    message: str
    project_id: Optional[uuid.UUID] = None


# ──────────────────────────────────────────────
# INFRASTRUCTURE PLAN SCHEMAS
# ──────────────────────────────────────────────

class InfrastructurePlanUpdate(BaseModel):
    region: Optional[str] = None
    component_id: Optional[str] = None
    service: Optional[str] = None
    tier: Optional[str] = None


class InfrastructurePlanApproval(BaseModel):
    note: Optional[str] = Field(default=None, max_length=500)


class InfrastructurePlanResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    provider: str
    region: str
    status: str
    revision: int
    plan: dict
    approval_note: Optional[str] = None
    approved_at: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class KnowledgeGraphResponse(BaseModel):
    project_id: uuid.UUID
    plan_revision: Optional[int] = None
    graph: dict
    generated_at: Optional[str] = None


class DigitalTwinSimulationResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    plan_revision: Optional[int] = None
    model: str
    status: str
    risk_score: int
    risk_level: str
    summary: str
    snapshot: dict
    checks: List[dict]
    proposed_changes: List[str] = []
    created_at: Optional[str] = None


class DecisionAccuracyResponse(BaseModel):
    available: bool
    outcome_accuracy_percent: Optional[float] = None
    evaluated_deployments: int
    successful_deployments: int
    failed_deployments: int
    pending_deployments: int
    methodology: str



# ──────────────────────────────────────────────
# DEPLOYMENT RECOMMENDATION SCHEMAS
# ──────────────────────────────────────────────

class DeploymentRecommendationResponse(BaseModel):
    id: uuid.UUID
    project_id: Optional[uuid.UUID] = None
    repository_full_name: str
    recommended_target: Optional[str] = None
    azure_configuration: dict = {}
    environment_variables: List[str] = []
    scaling_recommendation: dict = {}
    database_recommendation: dict = {}
    estimated_deployment_time: Optional[str] = None
    created_at: Optional[str] = None
    recommended_compute_tier: Optional[str] = None
    estimated_cost: Optional[str] = None
    recommended_region: Optional[str] = None
    expected_traffic: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


# ──────────────────────────────────────────────
# DEPLOYMENT FAILURE ANALYSIS SCHEMAS
# ──────────────────────────────────────────────

class FailureAnalysisResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    deployment_id: uuid.UUID
    failure_summary: str
    root_cause: str
    severity: str
    recommended_fix: str
    step_by_step_resolution: List[str] = []
    confidence: Optional[int] = 95
    impact: Optional[str] = None
    created_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


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

    model_config = ConfigDict(from_attributes=True)

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

    model_config = ConfigDict(from_attributes=True)

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

    model_config = ConfigDict(from_attributes=True)

class EnvVarCreate(BaseModel):
    key: str = Field(..., min_length=1, max_length=255, pattern=r"^[A-Z][A-Z0-9_]*$")
    value: str = Field(..., min_length=1, max_length=65536)
    is_secret: bool = False

class TelemetryMetricResponse(BaseModel):
    cpu: List[dict] = []
    memory: List[dict] = []
    uptime: str = "No data"
    error_rate: str = "No data"
    response_time: str = "No data"
    request_count: int = 0


# ──────────────────────────────────────────────
# COLLABORATION & DOMAIN SCHEMAS
# ──────────────────────────────────────────────

class ProjectDomainCreate(BaseModel):
    name: str

class ProjectMemberCreate(BaseModel):
    email: EmailStr
    role: str


# ──────────────────────────────────────────────
# DATABASE INSTANCE SCHEMAS
# ──────────────────────────────────────────────

class DatabaseInstanceResponse(BaseModel):
    id: uuid.UUID
    project_id: uuid.UUID
    type: str
    db_name: str
    username: str
    host: str
    port: int
    connection_string: str
    status: str
    created_at: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class SelfHealRequest(BaseModel):
    action: str
