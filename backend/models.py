import uuid
from datetime import datetime
from sqlalchemy import (
    BigInteger, Column, String, DateTime, Text, Integer, Float, Boolean,
    CheckConstraint, ForeignKey, JSON, Enum as SAEnum, Index, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import relationship, declarative_base
import enum

Base = declarative_base()
POSTGRES_JSON = JSON().with_variant(JSONB(), "postgresql")


# ──────────────────────────────────────────────
# ENUMS
# ──────────────────────────────────────────────

class ProjectStatus(str, enum.Enum):
    active = "active"
    archived = "archived"
    deploying = "deploying"
    failed = "failed"


class DeploymentStatus(str, enum.Enum):
    queued = "queued"
    building = "building"
    deploying = "deploying"
    running = "running"
    failed = "failed"
    stopped = "stopped"
    rolled_back = "rolled_back"


class DeploymentEnv(str, enum.Enum):
    production = "production"
    staging = "staging"
    development = "development"


class LogLevel(str, enum.Enum):
    INFO = "INFO"
    WARN = "WARN"
    ERROR = "ERROR"
    DEBUG = "DEBUG"


class NotificationType(str, enum.Enum):
    info = "info"
    success = "success"
    warning = "warning"
    critical = "critical"


class NotificationCategory(str, enum.Enum):
    deployment = "deployment"
    security = "security"
    scaling = "scaling"
    incident = "incident"
    ai = "ai"
    system = "system"


class AIActionType(str, enum.Enum):
    scaling = "scaling"
    security = "security"
    deployment = "deployment"
    optimization = "optimization"
    healing = "healing"
    monitoring = "monitoring"


class AIActionSeverity(str, enum.Enum):
    info = "info"
    warning = "warning"
    success = "success"
    critical = "critical"


class AIActionStatus(str, enum.Enum):
    pending = "pending"
    applied = "applied"
    dismissed = "dismissed"


class AzureConnectionStatus(str, enum.Enum):
    pending = "pending"
    connected = "connected"
    revoked = "revoked"
    error = "error"


class RiskTier(str, enum.Enum):
    low = "low"
    high = "high"


class ApprovalStatus(str, enum.Enum):
    not_required = "not_required"
    pending = "pending"
    approved = "approved"
    denied = "denied"


class AuditResultStatus(str, enum.Enum):
    success = "success"
    failed = "failed"
    pending = "pending"


class DeploymentJobStatus(str, enum.Enum):
    queued = "queued"
    cloning = "cloning"
    generating_terraform = "generating_terraform"
    terraform_init = "terraform_init"
    terraform_plan = "terraform_plan"
    awaiting_approval = "awaiting_approval"
    terraform_apply = "terraform_apply"
    deploying_app = "deploying_app"
    health_check = "health_check"
    monitoring_setup = "monitoring_setup"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"


# ──────────────────────────────────────────────
# USERS
# ──────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    first_name = Column(Text, nullable=True)
    last_name = Column(Text, nullable=True)
    email = Column(Text, unique=True, nullable=False, index=True)
    password_hash = Column(Text, nullable=True)
    provider = Column(Text, default="local")
    provider_id = Column(Text, nullable=True)
    avatar_url = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    plan = Column(Text, default="starter")
    # Legacy API-key columns are retained for schema compatibility. API-key
    # authentication and credential generation are not currently available.
    api_key = Column(Text, nullable=True, unique=True)
    api_key_prefix = Column(Text, nullable=True)
    refresh_token = Column(Text, nullable=True)
    last_primary_auth_at = Column(DateTime, nullable=True)

    # MFA secrets are Fernet-encrypted at rest. Recovery codes are bcrypt
    # hashes and are consumed after a successful use.
    mfa_enabled = Column(Boolean, nullable=False, default=False)
    mfa_secret_encrypted = Column(Text, nullable=True)
    mfa_setup_secret_encrypted = Column(Text, nullable=True)
    mfa_setup_expires_at = Column(DateTime, nullable=True)
    mfa_recovery_code_hashes = Column(JSON, default=list)
    mfa_last_used_counter = Column(Integer, nullable=True)
    mfa_challenge_id = Column(Text, nullable=True)
    mfa_challenge_expires_at = Column(DateTime, nullable=True)
    mfa_method = Column(Text, nullable=False, default="totp")  # "totp" or "email"

    # Email verification
    email_verified = Column(Boolean, nullable=False, default=False)
    email_verification_token = Column(Text, nullable=True)  # SHA-256 hashed
    email_verification_expires_at = Column(DateTime, nullable=True)

    # Phone verification is stored separately from MFA. Phone numbers are
    # normalized to E.164 before persistence and OTPs are bcrypt-hashed.
    phone_number = Column(Text, nullable=True, unique=True, index=True)
    phone_verified = Column(Boolean, nullable=False, default=False)
    phone_otp_hash = Column(Text, nullable=True)
    phone_otp_expires_at = Column(DateTime, nullable=True)
    phone_otp_attempts = Column(Integer, nullable=False, default=0)
    phone_otp_last_sent_at = Column(DateTime, nullable=True)
    phone_verification_challenge_id = Column(Text, nullable=True)
    phone_verification_context = Column(Text, nullable=True)

    # Database-backed lockout complements the per-IP rate limiter and prevents
    # credential stuffing from simply rotating source addresses.
    failed_login_count = Column(Integer, nullable=False, default=0)
    login_locked_until = Column(DateTime, nullable=True)

    # Email OTP for MFA
    email_otp_hash = Column(Text, nullable=True)  # bcrypt hashed
    email_otp_expires_at = Column(DateTime, nullable=True)

    # GitHub OAuth fields
    github_id = Column(Text, nullable=True, unique=True, index=True)
    github_username = Column(Text, nullable=True)
    github_avatar_url = Column(Text, nullable=True)
    github_access_token_encrypted = Column(Text, nullable=True)  # Fernet-encrypted
    github_connected = Column(Boolean, default=False)
    google_id = Column(Text, nullable=True, unique=True, index=True)

    # Relationships
    projects = relationship("Project", back_populates="user", cascade="all, delete-orphan")
    deployments = relationship("Deployment", back_populates="user", cascade="all, delete-orphan")
    notifications = relationship("Notification", back_populates="user", cascade="all, delete-orphan")
    ai_actions = relationship("AIAction", back_populates="user", cascade="all, delete-orphan")
    settings = relationship("UserSettings", back_populates="user", uselist=False, cascade="all, delete-orphan")
    repositories = relationship("Repository", back_populates="user", cascade="all, delete-orphan")
    activity_events = relationship(
        "ActivityEvent",
        back_populates="user",
        passive_deletes=True,
    )
    deployment_recommendations = relationship("DeploymentRecommendation", back_populates="user", cascade="all, delete-orphan")
    failure_analyses = relationship("FailureAnalysis", back_populates="user", cascade="all, delete-orphan")
    azure_connections = relationship("UserAzureConnection", back_populates="user", cascade="all, delete-orphan")
    gke_connections = relationship("UserGkeConnection", back_populates="user", cascade="all, delete-orphan")
    billing_operations = relationship("BillingOperation", back_populates="user", cascade="all, delete-orphan")
    code_uploads = relationship("CodeUpload", back_populates="user", cascade="all, delete-orphan")
    audit_log_entries = relationship("AuditLogEntry", back_populates="user", cascade="all, delete-orphan")
    pending_approvals = relationship("PendingApproval", back_populates="user", cascade="all, delete-orphan")
    tenant_memberships = relationship("TenantMembership", back_populates="user", cascade="all, delete-orphan")
    requested_operation_runs = relationship("OperationRun", back_populates="requested_by_user")
    created_artifacts = relationship("Artifact", back_populates="created_by_user")

    def to_dict(self):
        return {
            "id": str(self.id),
            "first_name": self.first_name,
            "last_name": self.last_name,
            "email": self.email,
            "provider": self.provider,
            "provider_id": self.provider_id,
            "avatar_url": self.avatar_url,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "plan": self.plan,
            "github_username": self.github_username,
            "github_avatar_url": self.github_avatar_url,
            "github_connected": self.github_connected or False,
            "mfa_enabled": self.mfa_enabled or False,
            "mfa_method": self.mfa_method or "totp",
            "email_verified": self.email_verified or False,
            "phone_verified": self.phone_verified or False,
        }


# ──────────────────────────────────────────────
# PROJECTS (connected repos / apps)
# ──────────────────────────────────────────────

# ----------------------------------------------------------------
# TENANTS AND OPERATION HISTORY
# ----------------------------------------------------------------

class Tenant(Base):
    """A ZeroOps data-isolation boundary.

    This is deliberately independent from ``UserAzureConnection.tenant_id``.
    That legacy value identifies a customer's Microsoft Entra tenant, while
    this model identifies a ZeroOps SaaS tenant.
    """

    __tablename__ = "tenants"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    display_name = Column(Text, nullable=False)
    kind = Column(Text, nullable=False, default="personal")
    status = Column(Text, nullable=False, default="active")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    memberships = relationship("TenantMembership", back_populates="tenant", cascade="all, delete-orphan")
    operation_runs = relationship("OperationRun", back_populates="tenant", cascade="all, delete-orphan")
    artifacts = relationship("Artifact", back_populates="tenant", cascade="all, delete-orphan")
    activity_events = relationship("ActivityEvent", back_populates="tenant")


class TenantMembership(Base):
    __tablename__ = "tenant_memberships"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    role = Column(Text, nullable=False, default="member")
    status = Column(Text, nullable=False, default="active")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="memberships")
    user = relationship("User", back_populates="tenant_memberships")

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_tenant_memberships_tenant_user"),
        Index("ix_tenant_memberships_user_status", "user_id", "status"),
        Index("ix_tenant_memberships_tenant_status", "tenant_id", "status"),
    )


class OperationRun(Base):
    """A durable, tenant-owned record for an analysis or infrastructure run.

    Only digests and redacted summaries belong here. Repository contents,
    credentials, Terraform state, raw plans, and unredacted model inputs do
    not belong in the relational history schema.
    """

    __tablename__ = "operation_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    requested_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    parent_operation_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("operation_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    operation_type = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="queued")
    source_revision = Column(Text, nullable=True)
    input_digest = Column(String(64), nullable=True)
    idempotency_key = Column(String(128), nullable=True)
    summary = Column(POSTGRES_JSON, nullable=False, default=dict)
    model_provider = Column(Text, nullable=True)
    model_name = Column(Text, nullable=True)
    model_version = Column(Text, nullable=True)
    prompt_version = Column(Text, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    model_cost_microusd = Column(BigInteger, nullable=True)
    error_code = Column(Text, nullable=True)
    redacted_error = Column(Text, nullable=True)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    tenant = relationship("Tenant", back_populates="operation_runs")
    project = relationship("Project")
    requested_by_user = relationship("User", back_populates="requested_operation_runs")
    parent_operation_run = relationship("OperationRun", remote_side=[id])
    artifacts = relationship(
        "Artifact",
        back_populates="operation_run",
        cascade="all, delete-orphan",
        order_by="Artifact.created_at",
    )
    activity_events = relationship(
        "ActivityEvent",
        back_populates="operation_run",
        order_by="ActivityEvent.created_at",
    )

    __table_args__ = (
        Index("ix_operation_runs_tenant_created", "tenant_id", "created_at"),
        Index("ix_operation_runs_tenant_status", "tenant_id", "status"),
        Index("ix_operation_runs_project_id", "project_id"),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_operation_runs_tenant_idempotency"),
        CheckConstraint(
            "input_digest IS NULL OR input_digest ~ '^[0-9a-f]{64}$'",
            name="ck_operation_runs_input_digest",
        ).ddl_if(dialect="postgresql"),
    )


class Artifact(Base):
    """Immutable metadata for a tenant-owned object in Azure Blob Storage."""

    __tablename__ = "artifacts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    artifact_key = Column(UUID(as_uuid=True), nullable=False, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    operation_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("operation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    kind = Column(Text, nullable=False)
    display_name = Column(Text, nullable=False)
    content_type = Column(Text, nullable=False, default="application/octet-stream")
    storage_container = Column(String(63), nullable=False)
    storage_path = Column(Text, nullable=False)
    sha256_digest = Column(String(64), nullable=False)
    size_bytes = Column(BigInteger, nullable=False)
    version = Column(Integer, nullable=False, default=1)
    access_scope = Column(Text, nullable=False, default="user")
    sanitization_status = Column(Text, nullable=False, default="sanitized")
    artifact_metadata = Column("metadata", POSTGRES_JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    expires_at = Column(DateTime, nullable=True)

    tenant = relationship("Tenant", back_populates="artifacts")
    operation_run = relationship("OperationRun", back_populates="artifacts")
    project = relationship("Project")
    created_by_user = relationship("User", back_populates="created_artifacts")

    __table_args__ = (
        UniqueConstraint("tenant_id", "artifact_key", "version", name="uq_artifacts_tenant_key_version"),
        UniqueConstraint("storage_container", "storage_path", name="uq_artifacts_storage_locator"),
        Index("ix_artifacts_tenant_created", "tenant_id", "created_at"),
        Index("ix_artifacts_operation_run_id", "operation_run_id"),
        Index("ix_artifacts_sha256_digest", "sha256_digest"),
        CheckConstraint(
            "sha256_digest ~ '^[0-9a-f]{64}$'",
            name="ck_artifacts_sha256",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint("size_bytes >= 0", name="ck_artifacts_size"),
        CheckConstraint("version >= 1", name="ck_artifacts_version"),
    )


class Project(Base):
    __tablename__ = "projects"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)                  # e.g. "web-app"
    full_name = Column(Text, nullable=False)              # e.g. "owner/repository"
    repo_url = Column(Text, nullable=True)                # https://github.com/owner/repository
    framework = Column(Text, default="Next.js")
    language = Column(Text, default="TypeScript")
    branch = Column(Text, default="main")
    region = Column(Text, default="eastus")
    status = Column(Text, default=ProjectStatus.active.value)
    source_type = Column(Text, default="github")
    source_path = Column(Text, nullable=True)
    last_deployed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    custom_domains = Column(JSON, default=list)
    members = Column(JSON, default=list)

    # Relationships
    user = relationship("User", back_populates="projects")
    deployments = relationship("Deployment", back_populates="project", cascade="all, delete-orphan", order_by="Deployment.started_at.desc()")
    ai_analyses = relationship("AIAnalysis", back_populates="project", cascade="all, delete-orphan")
    ai_actions = relationship("AIAction", back_populates="project", cascade="all, delete-orphan")
    environments = relationship("Environment", back_populates="project", cascade="all, delete-orphan")
    activity_events = relationship(
        "ActivityEvent",
        back_populates="project",
        passive_deletes=True,
    )
    deployment_recommendations = relationship("DeploymentRecommendation", back_populates="project", cascade="all, delete-orphan")
    failure_analyses = relationship("FailureAnalysis", back_populates="project", cascade="all, delete-orphan")
    databases = relationship("DatabaseInstance", back_populates="project", cascade="all, delete-orphan")
    infrastructure_plan = relationship("InfrastructurePlan", back_populates="project", uselist=False, cascade="all, delete-orphan")
    knowledge_graph_snapshots = relationship("KnowledgeGraphSnapshot", back_populates="project", cascade="all, delete-orphan")
    digital_twin_simulations = relationship("DigitalTwinSimulation", back_populates="project", cascade="all, delete-orphan")
    decision_evaluations = relationship("DecisionEvaluation", back_populates="project", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_projects_user_id", "user_id"),
    )


# ──────────────────────────────────────────────
# INFRASTRUCTURE PLANS (customer-facing architecture, never IaC source)
# ──────────────────────────────────────────────

class InfrastructurePlan(Base):
    """The reviewed architecture decision record for one project.

    ``plan_data`` deliberately contains product-facing resource decisions only.
    Terraform source and Azure credentials are generated and handled by the
    internal deployment worker; neither belongs in this model or its API.
    """

    __tablename__ = "infrastructure_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True)
    provider = Column(Text, nullable=False, default="azure")
    region = Column(Text, nullable=False)
    status = Column(Text, nullable=False, default="draft")
    revision = Column(Integer, nullable=False, default=1)
    plan_data = Column(JSON, nullable=False, default=dict)
    cost_estimate = Column(JSON, nullable=True)
    security_score = Column(Integer, nullable=True)
    performance_score = Column(Integer, nullable=True)
    reliability_score = Column(Integer, nullable=True)
    estimated_deploy_time = Column(Text, nullable=True)
    ai_explanations = Column(JSON, nullable=True)
    approval_note = Column(Text, nullable=True)
    approved_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User")
    project = relationship("Project", back_populates="infrastructure_plan")

    __table_args__ = (
        Index("ix_infrastructure_plans_user_id", "user_id"),
        Index("ix_infrastructure_plans_project_id", "project_id"),
    )


# ----------------------------------------------------------------
# DECISION INTELLIGENCE (evidence graph, preflight simulations, outcomes)
# ----------------------------------------------------------------

class KnowledgeGraphSnapshot(Base):
    """An auditable, redacted relationship graph for a project revision.

    Node properties intentionally contain source facts and architecture choices,
    never repository contents, cloud credentials, or environment values.
    """

    __tablename__ = "knowledge_graph_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    plan_revision = Column(Integer, nullable=True)
    graph_data = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    project = relationship("Project", back_populates="knowledge_graph_snapshots")

    __table_args__ = (
        Index("ix_knowledge_graph_snapshots_user_id", "user_id"),
        Index("ix_knowledge_graph_snapshots_project_id", "project_id"),
        Index("ix_knowledge_graph_snapshots_project_revision", "project_id", "plan_revision"),
    )


class DigitalTwinSimulation(Base):
    """A non-mutating preflight result for an architecture plan revision."""

    __tablename__ = "digital_twin_simulations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    infrastructure_plan_id = Column(UUID(as_uuid=True), ForeignKey("infrastructure_plans.id", ondelete="SET NULL"), nullable=True)
    plan_revision = Column(Integer, nullable=True)
    status = Column(Text, nullable=False)
    risk_score = Column(Integer, nullable=False)
    risk_level = Column(Text, nullable=False)
    snapshot = Column(JSON, nullable=False, default=dict)
    checks = Column(JSON, nullable=False, default=list)
    summary = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User")
    project = relationship("Project", back_populates="digital_twin_simulations")
    infrastructure_plan = relationship("InfrastructurePlan")

    __table_args__ = (
        Index("ix_digital_twin_simulations_user_id", "user_id"),
        Index("ix_digital_twin_simulations_project_id", "project_id"),
        Index("ix_digital_twin_simulations_project_revision", "project_id", "plan_revision"),
    )


class DecisionEvaluation(Base):
    """Records a real deployment outcome so accuracy is measured, not asserted."""

    __tablename__ = "decision_evaluations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    infrastructure_plan_id = Column(UUID(as_uuid=True), ForeignKey("infrastructure_plans.id", ondelete="SET NULL"), nullable=True)
    deployment_id = Column(UUID(as_uuid=True), ForeignKey("deployments.id", ondelete="SET NULL"), nullable=True, unique=True)
    plan_revision = Column(Integer, nullable=True)
    decision_type = Column(Text, nullable=False, default="architecture_deployment")
    recommendation = Column(JSON, nullable=False, default=dict)
    status = Column(Text, nullable=False, default="pending")
    outcome_metadata = Column(JSON, nullable=False, default=dict)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = relationship("User")
    project = relationship("Project", back_populates="decision_evaluations")
    infrastructure_plan = relationship("InfrastructurePlan")
    deployment = relationship("Deployment")

    __table_args__ = (
        Index("ix_decision_evaluations_user_id", "user_id"),
        Index("ix_decision_evaluations_project_id", "project_id"),
        Index("ix_decision_evaluations_status", "status"),
    )


# ──────────────────────────────────────────────
# DEPLOYMENTS
# ──────────────────────────────────────────────

class Deployment(Base):
    __tablename__ = "deployments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    status = Column(Text, default=DeploymentStatus.queued.value)
    environment = Column(Text, default=DeploymentEnv.production.value)
    branch = Column(Text, default="main")
    version = Column(Text, nullable=True)                 # e.g. "v1.0.0"
    commit_sha = Column(Text, nullable=True)
    image = Column(Text, nullable=True)                   # e.g. "acr.azurecr.io/web:v1.0.0"
    duration_seconds = Column(Integer, nullable=True)
    live_url = Column(Text, nullable=True)
    deployed_by = Column(Text, default="AI Auto-Deploy")
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    failure_reason = Column(Text, nullable=True)
    infrastructure_metadata = Column(JSON, nullable=True)

    # Relationships
    user = relationship("User", back_populates="deployments")
    project = relationship("Project", back_populates="deployments")
    logs = relationship("DeploymentLog", back_populates="deployment", cascade="all, delete-orphan", order_by="DeploymentLog.line_number")
    metrics = relationship("DeploymentMetric", back_populates="deployment", cascade="all, delete-orphan")
    failure_analysis = relationship("FailureAnalysis", back_populates="deployment", uselist=False, cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_deployments_user_id", "user_id"),
        Index("ix_deployments_project_id", "project_id"),
    )


# ──────────────────────────────────────────────
# DEPLOYMENT LOGS
# ──────────────────────────────────────────────

class DeploymentLog(Base):
    __tablename__ = "deployment_logs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deployment_id = Column(UUID(as_uuid=True), ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False)
    line_number = Column(Integer, nullable=False)
    level = Column(Text, default=LogLevel.INFO.value)
    message = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    # Relationships
    deployment = relationship("Deployment", back_populates="logs")

    __table_args__ = (
        Index("ix_deployment_logs_deployment_id", "deployment_id"),
    )


# ──────────────────────────────────────────────
# NOTIFICATIONS
# ──────────────────────────────────────────────

class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    title = Column(Text, nullable=False)
    message = Column(Text, nullable=False)
    type = Column(Text, default=NotificationType.info.value)        # info, success, warning, critical
    category = Column(Text, default=NotificationCategory.system.value)  # deployment, security, scaling, incident, ai, system
    read = Column(Boolean, default=False)
    action_url = Column(Text, nullable=True)   # Optional link to relevant page
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="notifications")

    __table_args__ = (
        Index("ix_notifications_user_id", "user_id"),
        Index("ix_notifications_user_read", "user_id", "read"),
    )


# ──────────────────────────────────────────────
# AI AUTONOMOUS ACTIONS
# ──────────────────────────────────────────────

class AIAction(Base):
    __tablename__ = "ai_actions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    type = Column(Text, default=AIActionType.monitoring.value)
    severity = Column(Text, default=AIActionSeverity.info.value)
    message = Column(Text, nullable=False)
    recommendation = Column(Text, nullable=True)
    status = Column(Text, default=AIActionStatus.pending.value)
    icon = Column(Text, default="Brain")  # Lucide icon name
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="ai_actions")
    project = relationship("Project", back_populates="ai_actions")

    __table_args__ = (
        Index("ix_ai_actions_user_id", "user_id"),
    )


# ──────────────────────────────────────────────
# AI ANALYSIS RESULTS
# ──────────────────────────────────────────────

class AIAnalysis(Base):
    __tablename__ = "ai_analyses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    framework = Column(Text, nullable=True)
    framework_version = Column(Text, nullable=True)
    language = Column(Text, nullable=True)
    risk_score = Column(Integer, default=0)
    confidence = Column(Integer, default=0)
    cpu_recommendation = Column(Text, nullable=True)
    memory_recommendation = Column(Text, nullable=True)
    storage_recommendation = Column(Text, nullable=True)
    port = Column(Text, nullable=True)
    dependencies = Column(JSON, default=list)       # ["next@16.2.6", "react@19"]
    vulnerabilities = Column(JSON, default=list)     # ["CVE-2026-1234: ..."]
    dockerfile = Column(Text, nullable=True)
    kubernetes_manifest = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Real AI Analysis fields
    runtime = Column(Text, nullable=True)
    package_manager = Column(Text, nullable=True)
    docker_support = Column(Boolean, default=False)
    monorepo_structure = Column(Text, nullable=True)
    database_dependencies = Column(JSON, default=list)
    deployment_strategy = Column(Text, nullable=True)
    build_commands = Column(Text, nullable=True)
    start_commands = Column(Text, nullable=True)
    environment_variables = Column(JSON, default=list)
    explanation = Column(Text, nullable=True)
    recommended_compute_tier = Column(Text, nullable=True)
    estimated_cost = Column(Text, nullable=True)
    recommended_region = Column(Text, nullable=True)
    expected_traffic = Column(Text, nullable=True)
    pricing_breakdown = Column(JSON, nullable=True)

    # Relationships
    project = relationship("Project", back_populates="ai_analyses")

    __table_args__ = (
        Index("ix_ai_analyses_project_id", "project_id"),
    )


# ──────────────────────────────────────────────
# USER SETTINGS
# ──────────────────────────────────────────────

class UserSettings(Base):
    __tablename__ = "user_settings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    predictive_scaling = Column(Boolean, default=False)
    auto_rollback = Column(Boolean, default=False)
    ai_threat_mitigation = Column(Boolean, default=False)
    auto_oom_restart = Column(Boolean, default=False)
    slack_notifications = Column(Boolean, default=False)
    email_alerts = Column(Boolean, default=True)
    theme = Column(Text, default="dark")

    # Relationships
    user = relationship("User", back_populates="settings")

    __table_args__ = (
        Index("ix_user_settings_user_id", "user_id"),
    )


# ──────────────────────────────────────────────
# CONNECTED REPOSITORIES
# ──────────────────────────────────────────────

class Repository(Base):
    __tablename__ = "repositories"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, nullable=False)
    full_name = Column(Text, nullable=False)
    html_url = Column(Text, nullable=True)
    private = Column(Boolean, default=False)
    language = Column(Text, nullable=True)
    default_branch = Column(Text, default="main")
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="repositories")

    __table_args__ = (
        Index("ix_repositories_user_id", "user_id"),
    )


# ──────────────────────────────────────────────
# ENVIRONMENTS
# ──────────────────────────────────────────────

class Environment(Base):
    __tablename__ = "environments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    name = Column(Text, default="production")  # production, staging, development
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    project = relationship("Project", back_populates="environments")
    variables = relationship("EnvironmentVariable", back_populates="environment", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_environments_project_id", "project_id"),
    )


# ──────────────────────────────────────────────
# ENVIRONMENT VARIABLES
# ──────────────────────────────────────────────

class EnvironmentVariable(Base):
    __tablename__ = "environment_variables"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    environment_id = Column(UUID(as_uuid=True), ForeignKey("environments.id", ondelete="CASCADE"), nullable=False)
    key = Column(String(255), nullable=False)
    value = Column(Text, nullable=False)
    is_secret = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    environment = relationship("Environment", back_populates="variables")

    __table_args__ = (
        Index("ix_environment_variables_environment_id", "environment_id"),
    )


# ──────────────────────────────────────────────
# DEPLOYMENT METRICS (Real telemetry history)
# ──────────────────────────────────────────────

class DeploymentMetric(Base):
    __tablename__ = "deployment_metrics"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    deployment_id = Column(UUID(as_uuid=True), ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    cpu_utilization = Column(Float, default=0.0)
    memory_utilization = Column(Float, default=0.0)
    request_count = Column(Integer, default=0)
    error_rate = Column(Float, default=0.0)
    response_time_ms = Column(Integer, default=0)
    timestamp = Column(DateTime, default=datetime.utcnow)

    # Relationships
    deployment = relationship("Deployment", back_populates="metrics")

    __table_args__ = (
        Index("ix_deployment_metrics_deployment_id", "deployment_id"),
        Index("ix_deployment_metrics_project_id", "project_id"),
    )


# ──────────────────────────────────────────────
# ACTIVITY EVENTS
# ──────────────────────────────────────────────

class ActivityEvent(Base):
    __tablename__ = "activity_events"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True)
    operation_run_id = Column(
        UUID(as_uuid=True),
        ForeignKey("operation_runs.id", ondelete="SET NULL"),
        nullable=True,
    )
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    action = Column(Text, nullable=False)
    details = Column(Text, nullable=True)
    actor_type = Column(Text, nullable=False, default="user")
    actor_id = Column(String(128), nullable=True)
    event_data = Column(POSTGRES_JSON, nullable=False, default=dict)
    external_event_id = Column(String(128), nullable=True)
    event_fingerprint = Column(String(64), nullable=True)
    sequence_number = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    tenant = relationship("Tenant", back_populates="activity_events")
    operation_run = relationship("OperationRun", back_populates="activity_events")
    user = relationship("User", back_populates="activity_events")
    project = relationship("Project", back_populates="activity_events")

    __table_args__ = (
        Index("ix_activity_events_user_id", "user_id"),
        Index("ix_activity_events_tenant_created", "tenant_id", "created_at"),
        Index("ix_activity_events_operation_created", "operation_run_id", "created_at"),
        UniqueConstraint(
            "operation_run_id",
            "sequence_number",
            name="uq_activity_events_operation_sequence",
        ),
        UniqueConstraint(
            "tenant_id",
            "external_event_id",
            name="uq_activity_events_tenant_external_event",
        ),
        CheckConstraint(
            "event_fingerprint IS NULL OR event_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_activity_events_fingerprint",
        ).ddl_if(dialect="postgresql"),
    )


# ──────────────────────────────────────────────
# REVOKED TOKENS (Blacklist for logout invalidation)
# ──────────────────────────────────────────────

class RevokedToken(Base):
    __tablename__ = "revoked_tokens"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    token = Column(Text, nullable=False, unique=True, index=True)
    expires_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# ──────────────────────────────────────────────
# AZURE BYOS – USER CONNECTIONS
# ──────────────────────────────────────────────

class UserAzureConnection(Base):
    __tablename__ = "user_azure_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(Text, nullable=False)
    subscription_id = Column(Text, nullable=False)
    client_id = Column(Text, nullable=True)
    # NOTE: client_secret is NEVER stored in the database.
    # It is stored exclusively in Azure Key Vault at path: zeroops-{user_id}-sp-client-secret
    connection_status = Column(
        Text, default=AzureConnectionStatus.pending.value
    )  # pending, connected, revoked, error
    region = Column(Text, default="eastus")
    resource_group = Column(Text, nullable=True)
    acr_login_server = Column(Text, nullable=True)
    # Existing Linux App Service plan selected by the account owner for customer apps.
    app_service_plan = Column(Text, nullable=True)
    # Legacy field retained only so existing databases can be upgraded safely.
    container_apps_environment = Column(Text, nullable=True)
    aks_cluster_name = Column(Text, nullable=True)
    namespace_prefix = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="azure_connections")

    __table_args__ = (
        Index("ix_user_azure_connections_user_id", "user_id"),
    )


# ──────────────────────────────────────────────
# AZURE BYOS AUDIT LOG
# ──────────────────────────────────────────────

class AuditLogEntry(Base):
    __tablename__ = "audit_log_entries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    agent_name = Column(Text, nullable=False)  # e.g. "pipeline", "scaling_agent"
    action_type = Column(Text, nullable=False)  # e.g. "aks_cluster_create", "resource_delete"
    parameters = Column(JSON, default=dict)  # Secrets MUST be redacted before storage
    risk_tier = Column(Text, default=RiskTier.low.value)  # "low" or "high"
    approval_status = Column(
        Text, default=ApprovalStatus.not_required.value
    )  # not_required, pending, approved, denied
    approved_by = Column(UUID(as_uuid=True), nullable=True)  # user_id of approver
    result_status = Column(
        Text, default=AuditResultStatus.pending.value
    )  # pending, success, failed
    result_detail = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="audit_log_entries")

    __table_args__ = (
        Index("ix_audit_log_entries_user_id", "user_id"),
        Index("ix_audit_log_entries_created_at", "created_at"),
    )


# ──────────────────────────────────────────────
# PENDING APPROVALS (high-risk action queue)
# ──────────────────────────────────────────────

class PendingApproval(Base):
    __tablename__ = "pending_approvals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    audit_log_id = Column(UUID(as_uuid=True), ForeignKey("audit_log_entries.id", ondelete="CASCADE"), nullable=False, unique=True)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    action_type = Column(Text, nullable=False)
    parameters = Column(JSON, default=dict)  # Secrets MUST be redacted
    raw_parameters = Column(JSON, default=dict)  # Real unredacted parameters for execution
    risk_tier = Column(Text, default=RiskTier.high.value)
    status = Column(Text, default=ApprovalStatus.pending.value)  # pending, approved, denied
    decided_by = Column(UUID(as_uuid=True), nullable=True)
    decided_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    audit_log = relationship("AuditLogEntry")
    user = relationship("User", back_populates="pending_approvals")

    __table_args__ = (
        Index("ix_pending_approvals_user_id", "user_id"),
        Index("ix_pending_approvals_status", "status"),
    )


# ──────────────────────────────────────────────
# GKE USER CONNECTIONS
# ──────────────────────────────────────────────

class UserGkeConnection(Base):
    __tablename__ = "user_gke_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    gcp_project_id = Column(Text, nullable=False)
    service_account_email = Column(Text, nullable=True)
    service_account_json_encrypted = Column(Text, nullable=True)
    location = Column(Text, default="us-central1")
    cluster_name = Column(Text, nullable=True)
    artifact_registry_host = Column(Text, nullable=True)
    artifact_registry_repository = Column(Text, nullable=True)
    namespace_prefix = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="gke_connections")

    __table_args__ = (
        Index("ix_user_gke_connections_user_id", "user_id"),
    )


# ──────────────────────────────────────────────
# BILLING OPERATIONS
# ──────────────────────────────────────────────

class BillingOperation(Base):
    __tablename__ = "billing_operations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    deployment_id = Column(UUID(as_uuid=True), ForeignKey("deployments.id", ondelete="SET NULL"), nullable=True)
    operation_type = Column(Text, nullable=False)
    status = Column(Text, default="pending_payment")
    amount_cents = Column(Integer, default=0)
    currency = Column(Text, default="usd")
    provider = Column(Text, nullable=True)
    provider_reference = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    paid_at = Column(DateTime, nullable=True)
    consumed_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="billing_operations")

    __table_args__ = (
        Index("ix_billing_operations_user_id", "user_id"),
        Index("ix_billing_operations_status", "status"),
    )


# ──────────────────────────────────────────────
# CODE UPLOADS
# ──────────────────────────────────────────────

class CodeUpload(Base):
    __tablename__ = "code_uploads"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    original_filename = Column(Text, nullable=False)
    storage_path = Column(Text, nullable=False)
    size_bytes = Column(Integer, nullable=False, default=0)
    checksum_sha256 = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="code_uploads")
    project = relationship("Project")

    __table_args__ = (
        Index("ix_code_uploads_user_id", "user_id"),
        Index("ix_code_uploads_project_id", "project_id"),
    )


# ──────────────────────────────────────────────
# DEPLOYMENT RECOMMENDATIONS
# ──────────────────────────────────────────────

class DeploymentRecommendation(Base):
    __tablename__ = "deployment_recommendations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=True)
    repository_full_name = Column(Text, nullable=False)
    recommended_target = Column(Text, nullable=True)
    azure_configuration = Column(JSON, default=dict)
    environment_variables = Column(JSON, default=list)
    scaling_recommendation = Column(JSON, default=dict)
    database_recommendation = Column(JSON, default=dict)
    estimated_deployment_time = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    recommended_compute_tier = Column(Text, nullable=True)
    estimated_cost = Column(Text, nullable=True)
    recommended_region = Column(Text, nullable=True)
    expected_traffic = Column(Text, nullable=True)

    # Relationships
    user = relationship("User", back_populates="deployment_recommendations")
    project = relationship("Project", back_populates="deployment_recommendations")

    __table_args__ = (
        Index("ix_deployment_recommendations_user_id", "user_id"),
        Index("ix_deployment_recommendations_project_id", "project_id"),
    )


# ──────────────────────────────────────────────
# DEPLOYMENT FAILURE ANALYSIS
# ──────────────────────────────────────────────

class FailureAnalysis(Base):
    __tablename__ = "failure_analyses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    deployment_id = Column(UUID(as_uuid=True), ForeignKey("deployments.id", ondelete="CASCADE"), nullable=False, unique=True)
    failure_summary = Column(Text, nullable=False)
    root_cause = Column(Text, nullable=False)
    severity = Column(Text, nullable=False)
    recommended_fix = Column(Text, nullable=False)
    step_by_step_resolution = Column(JSON, default=list)
    confidence = Column(Integer, default=0)
    impact = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="failure_analyses")
    project = relationship("Project", back_populates="failure_analyses")
    deployment = relationship("Deployment", back_populates="failure_analysis")

    __table_args__ = (
        Index("ix_failure_analyses_user_id", "user_id"),
        Index("ix_failure_analyses_project_id", "project_id"),
        Index("ix_failure_analyses_deployment_id", "deployment_id"),
    )


# ──────────────────────────────────────────────
# MANAGED DATABASE INSTANCES
# ──────────────────────────────────────────────

class DatabaseInstance(Base):
    __tablename__ = "database_instances"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    type = Column(Text, nullable=False)  # PostgreSQL, MySQL, MongoDB, Redis
    db_name = Column(Text, nullable=False)
    username = Column(Text, nullable=False)
    password = Column(Text, nullable=False)
    host = Column(Text, nullable=False)
    port = Column(Integer, nullable=False)
    connection_string = Column(Text, nullable=False)
    status = Column(Text, default="provisioning")  # provisioning, available, failed
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    project = relationship("Project", back_populates="databases")

    __table_args__ = (
        Index("ix_database_instances_project_id", "project_id"),
    )


# ──────────────────────────────────────────────
# DEPLOYMENT QUEUE JOBS
# ──────────────────────────────────────────────

class DeploymentJob(Base):
    __tablename__ = "deployment_jobs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    deployment_id = Column(UUID(as_uuid=True), ForeignKey("deployments.id", ondelete="SET NULL"), nullable=True)
    status = Column(Text, nullable=False, default="queued")  # queued, running, completed, failed
    cloud = Column(Text, nullable=False, default="azure")
    region = Column(Text, nullable=False)
    terraform_status = Column(Text, nullable=False, default="pending")  # pending, running, completed, failed
    deployment_status = Column(Text, nullable=False, default="pending")  # pending, running, completed, failed
    estimated_cost = Column(Text, nullable=True)
    terraform_path = Column(Text, nullable=True)
    logs = Column(Text, nullable=True)
    infrastructure_spec = Column(JSON, nullable=True)
    terraform_plan_output = Column(Text, nullable=True)
    live_url = Column(Text, nullable=True)
    failure_reason = Column(Text, nullable=True)
    worker_id = Column(Text, nullable=True)
    lease_token = Column(Text, nullable=True)
    lease_expires_at = Column(DateTime, nullable=True)
    heartbeat_at = Column(DateTime, nullable=True)
    attempt_count = Column(Integer, nullable=False, default=0)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    user = relationship("User")
    project = relationship("Project")
    deployment = relationship("Deployment")

    __table_args__ = (
        Index("ix_deployment_jobs_status", "status"),
        Index("ix_deployment_jobs_lease", "status", "lease_expires_at"),
        Index("ix_deployment_jobs_project_id", "project_id"),
    )

