import uuid
from datetime import datetime, timezone
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


class ExecutionStatus(str, enum.Enum):
    """Fail-closed lifecycle shared by durable pipeline work records."""

    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"
    skipped = "skipped"
    blocked = "blocked"
    unavailable = "unavailable"
    cancelled = "cancelled"


def utc_now() -> datetime:
    """Return an aware UTC timestamp for new production workflow records."""

    return datetime.now(timezone.utc)


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
    # Missing telemetry is NULL. Zero is a real observed value and must not be
    # manufactured by an ORM default when a source omits a measurement.
    cpu_utilization = Column(Float, nullable=True)
    memory_utilization = Column(Float, nullable=True)
    request_count = Column(Integer, nullable=True)
    error_rate = Column(Float, nullable=True)
    response_time_ms = Column(Integer, nullable=True)
    request_rate = Column(Float, nullable=True)
    availability_percent = Column(Float, nullable=True)
    pod_restarts = Column(Integer, nullable=True)
    pods_ready = Column(Integer, nullable=True)
    replica_count = Column(Integer, nullable=True)
    failed_pods = Column(Integer, nullable=True)
    source = Column(Text, nullable=True)
    deployment_health = Column(Text, nullable=True)
    timestamp = Column(DateTime, default=datetime.utcnow)

    # Relationships
    deployment = relationship("Deployment", back_populates="metrics")

    __table_args__ = (
        Index("ix_deployment_metrics_deployment_id", "deployment_id"),
        Index("ix_deployment_metrics_project_id", "project_id"),
        CheckConstraint(
            "request_rate IS NULL OR request_rate >= 0",
            name="ck_deployment_metrics_request_rate",
        ),
        CheckConstraint(
            "availability_percent IS NULL OR "
            "(availability_percent >= 0 AND availability_percent <= 100)",
            name="ck_deployment_metrics_availability",
        ),
        CheckConstraint(
            "(pod_restarts IS NULL OR pod_restarts >= 0) AND "
            "(pods_ready IS NULL OR pods_ready >= 0) AND "
            "(replica_count IS NULL OR replica_count >= 0) AND "
            "(failed_pods IS NULL OR failed_pods >= 0)",
            name="ck_deployment_metrics_pod_counts",
        ),
        CheckConstraint(
            "deployment_health IS NULL OR deployment_health IN "
            "('healthy', 'degraded', 'unhealthy', 'rollout_failed', 'unavailable', 'unknown')",
            name="ck_deployment_metrics_health",
        ),
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
    # Compatibility name retained for existing databases. New writes contain
    # only a versioned ciphertext envelope and are erased after execution.
    raw_parameters = Column(JSON, default=dict)
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


# ----------------------------------------------------------------
# DURABLE DEVSECOPS PIPELINE DOMAIN
# ----------------------------------------------------------------


class ProjectPipelineConfiguration(Base):
    """Versioned, project-owned controls for deterministic pipeline execution."""

    __tablename__ = "project_pipeline_configurations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    created_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    version = Column(Integer, nullable=False, default=1)
    enabled = Column(Boolean, nullable=False, default=True)
    trigger_mode = Column(String(16), nullable=False, default="manual")
    tracked_branch = Column(Text, nullable=False, default="main")
    auto_deploy = Column(Boolean, nullable=False, default=False)
    deployment_mode = Column(String(32), nullable=False, default="require_approval")
    require_production_approval = Column(Boolean, nullable=False, default=True)
    require_infrastructure_approval = Column(Boolean, nullable=False, default=True)
    run_dependency_install = Column(Boolean, nullable=False, default=True)
    run_code_quality = Column(Boolean, nullable=False, default=True)
    run_unit_tests = Column(Boolean, nullable=False, default=True)
    run_sast = Column(Boolean, nullable=False, default=True)
    run_dependency_scan = Column(Boolean, nullable=False, default=True)
    run_secret_scan = Column(Boolean, nullable=False, default=True)
    run_container_scan = Column(Boolean, nullable=False, default=True)
    run_iac_scan = Column(Boolean, nullable=False, default=True)
    generate_sbom = Column(Boolean, nullable=False, default=False)
    ai_failure_diagnosis = Column(Boolean, nullable=False, default=True)
    auto_retry_transient_failures = Column(Boolean, nullable=False, default=False)
    auto_rollback_enabled = Column(Boolean, nullable=False, default=False)
    config_digest = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    tenant = relationship("Tenant")
    project = relationship("Project")
    created_by_user = relationship("User", foreign_keys=[created_by_user_id])
    updated_by_user = relationship("User", foreign_keys=[updated_by_user_id])

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "project_id",
            "version",
            name="uq_pipeline_config_tenant_project_version",
        ),
        Index("ix_pipeline_config_project_version", "project_id", "version"),
        CheckConstraint("version >= 1", name="ck_pipeline_config_version"),
        CheckConstraint(
            "trigger_mode IN ('manual', 'push', 'manual_and_push', 'disabled')",
            name="ck_pipeline_config_trigger_mode",
        ),
        CheckConstraint(
            "deployment_mode IN ('validate_only', 'deploy_after_checks', 'require_approval')",
            name="ck_pipeline_config_deployment_mode",
        ),
        CheckConstraint(
            "config_digest IS NULL OR config_digest ~ '^[0-9a-f]{64}$'",
            name="ck_pipeline_config_digest",
        ).ddl_if(dialect="postgresql"),
    )


class PipelineRun(Base):
    """One immutable-source pipeline execution with an idempotent trigger."""

    __tablename__ = "pipeline_runs"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    deployment_id = Column(UUID(as_uuid=True), ForeignKey("deployments.id", ondelete="SET NULL"), nullable=True)
    operation_run_id = Column(UUID(as_uuid=True), ForeignKey("operation_runs.id", ondelete="SET NULL"), nullable=True)
    configuration_id = Column(
        UUID(as_uuid=True),
        ForeignKey("project_pipeline_configurations.id", ondelete="SET NULL"),
        nullable=True,
    )
    requested_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    idempotency_key = Column(String(128), nullable=False)
    trigger_type = Column(String(16), nullable=False, default="manual")
    status = Column(String(16), nullable=False, default=ExecutionStatus.queued.value)
    branch = Column(Text, nullable=False)
    source_revision = Column(String(64), nullable=False)
    previous_successful_revision = Column(String(64), nullable=True)
    target_type = Column(String(32), nullable=False, default="undecided")
    configuration_version = Column(Integer, nullable=False, default=1)
    current_stage_key = Column(String(64), nullable=True)
    repository_ai_required = Column(Boolean, nullable=False, default=False)
    repository_ai_used = Column(Boolean, nullable=False, default=False)
    approval_required = Column(Boolean, nullable=False, default=False)
    status_reason = Column(Text, nullable=True)
    failure_code = Column(String(64), nullable=True)
    redacted_failure = Column(Text, nullable=True)
    queued_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    cancelled_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    tenant = relationship("Tenant")
    project = relationship("Project")
    deployment = relationship("Deployment")
    operation_run = relationship("OperationRun")
    configuration = relationship("ProjectPipelineConfiguration")
    requested_by_user = relationship("User")
    stage_attempts = relationship(
        "PipelineStageAttempt",
        back_populates="pipeline_run",
        cascade="all, delete-orphan",
        order_by="PipelineStageAttempt.stage_order, PipelineStageAttempt.attempt_number",
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_pipeline_runs_tenant_idempotency"),
        Index("ix_pipeline_runs_project_created", "project_id", "created_at"),
        Index("ix_pipeline_runs_deployment_id", "deployment_id"),
        Index("ix_pipeline_runs_tenant_status", "tenant_id", "status"),
        CheckConstraint("configuration_version >= 1", name="ck_pipeline_runs_config_version"),
        CheckConstraint(
            "trigger_type IN ('manual', 'push', 'retry', 'api', 'remediation')",
            name="ck_pipeline_runs_trigger_type",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'skipped', "
            "'blocked', 'unavailable', 'cancelled')",
            name="ck_pipeline_runs_status",
        ),
        CheckConstraint(
            "status NOT IN ('failed', 'skipped', 'blocked', 'unavailable', 'cancelled') "
            "OR status_reason IS NOT NULL",
            name="ck_pipeline_runs_terminal_reason",
        ),
    )


class PipelineStageAttempt(Base):
    """A normalized attempt for one stage; core lifecycle never lives in JSON."""

    __tablename__ = "pipeline_stage_attempts"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    deployment_id = Column(UUID(as_uuid=True), ForeignKey("deployments.id", ondelete="SET NULL"), nullable=True)
    pipeline_run_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id", ondelete="CASCADE"), nullable=False)
    log_artifact_id = Column(UUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True)
    output_artifact_id = Column(UUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True)
    idempotency_key = Column(String(128), nullable=False)
    stage_key = Column(String(64), nullable=False)
    display_name = Column(Text, nullable=False)
    stage_order = Column(Integer, nullable=False)
    attempt_number = Column(Integer, nullable=False, default=1)
    is_required = Column(Boolean, nullable=False, default=True)
    status = Column(String(16), nullable=False, default=ExecutionStatus.queued.value)
    tool_name = Column(String(128), nullable=True)
    tool_version = Column(String(128), nullable=True)
    status_reason = Column(Text, nullable=True)
    failure_code = Column(String(64), nullable=True)
    redacted_error = Column(Text, nullable=True)
    evidence = Column(POSTGRES_JSON, nullable=False, default=list)
    result_metadata = Column(POSTGRES_JSON, nullable=False, default=dict)
    queued_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    tenant = relationship("Tenant")
    project = relationship("Project")
    deployment = relationship("Deployment")
    pipeline_run = relationship("PipelineRun", back_populates="stage_attempts")
    log_artifact = relationship("Artifact", foreign_keys=[log_artifact_id])
    output_artifact = relationship("Artifact", foreign_keys=[output_artifact_id])

    __table_args__ = (
        UniqueConstraint(
            "pipeline_run_id",
            "stage_key",
            "attempt_number",
            name="uq_pipeline_stage_attempt_run_stage_attempt",
        ),
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_pipeline_stage_attempt_tenant_idempotency"),
        Index("ix_pipeline_stage_attempts_run_order", "pipeline_run_id", "stage_order"),
        Index("ix_pipeline_stage_attempts_deployment_id", "deployment_id"),
        Index("ix_pipeline_stage_attempts_status", "status"),
        CheckConstraint("stage_order >= 1", name="ck_pipeline_stage_attempt_order"),
        CheckConstraint("attempt_number >= 1", name="ck_pipeline_stage_attempt_number"),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'skipped', "
            "'blocked', 'unavailable', 'cancelled')",
            name="ck_pipeline_stage_attempt_status",
        ),
        CheckConstraint(
            "status NOT IN ('failed', 'skipped', 'blocked', 'unavailable', 'cancelled') "
            "OR status_reason IS NOT NULL",
            name="ck_pipeline_stage_attempt_terminal_reason",
        ),
    )


class RepositoryAnalysisSnapshot(Base):
    """Redacted, fingerprinted repository facts for reuse across revisions."""

    __tablename__ = "repository_analysis_snapshots"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    deployment_id = Column(UUID(as_uuid=True), ForeignKey("deployments.id", ondelete="SET NULL"), nullable=True)
    pipeline_run_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id", ondelete="SET NULL"), nullable=True)
    reused_from_snapshot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("repository_analysis_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )
    idempotency_key = Column(String(128), nullable=False)
    source_revision = Column(String(64), nullable=False)
    repository_fingerprint = Column(String(64), nullable=False)
    architecture_fingerprint = Column(String(64), nullable=False)
    dependency_files_hash = Column(String(64), nullable=False)
    dockerfile_hash = Column(String(64), nullable=False)
    infrastructure_files_hash = Column(String(64), nullable=False)
    kubernetes_manifests_hash = Column(String(64), nullable=False)
    important_configuration_files_hash = Column(String(64), nullable=False)
    fingerprint_version = Column(String(64), nullable=False)
    analyzer_version = Column(String(64), nullable=False)
    analysis_mode = Column(String(16), nullable=False, default="deterministic")
    status = Column(String(16), nullable=False, default=ExecutionStatus.queued.value)
    ai_required = Column(Boolean, nullable=False, default=False)
    ai_used = Column(Boolean, nullable=False, default=False)
    application_framework = Column(Text, nullable=True)
    detected_services = Column(POSTGRES_JSON, nullable=False, default=list)
    environment_variable_names = Column(POSTGRES_JSON, nullable=False, default=list)
    summary = Column(POSTGRES_JSON, nullable=False, default=dict)
    evidence = Column(POSTGRES_JSON, nullable=False, default=list)
    error_code = Column(String(64), nullable=True)
    redacted_error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    tenant = relationship("Tenant")
    project = relationship("Project")
    deployment = relationship("Deployment")
    pipeline_run = relationship("PipelineRun")
    reused_from_snapshot = relationship("RepositoryAnalysisSnapshot", remote_side=[id])

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_repository_snapshots_tenant_idempotency"),
        UniqueConstraint(
            "tenant_id",
            "project_id",
            "source_revision",
            "repository_fingerprint",
            name="uq_repository_snapshots_revision_fingerprint",
        ),
        Index("ix_repository_snapshots_project_created", "project_id", "created_at"),
        Index("ix_repository_snapshots_architecture_fingerprint", "architecture_fingerprint"),
        CheckConstraint(
            "analysis_mode IN ('deterministic', 'model', 'reused')",
            name="ck_repository_snapshots_analysis_mode",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'skipped', "
            "'blocked', 'unavailable', 'cancelled')",
            name="ck_repository_snapshots_status",
        ),
        CheckConstraint(
            "repository_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_repository_snapshots_repository_fingerprint",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "architecture_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_repository_snapshots_architecture_fingerprint",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "dependency_files_hash ~ '^[0-9a-f]{64}$'",
            name="ck_repository_snapshots_dependency_hash",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "dockerfile_hash ~ '^[0-9a-f]{64}$'",
            name="ck_repository_snapshots_dockerfile_hash",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "infrastructure_files_hash ~ '^[0-9a-f]{64}$'",
            name="ck_repository_snapshots_infrastructure_hash",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "kubernetes_manifests_hash ~ '^[0-9a-f]{64}$'",
            name="ck_repository_snapshots_kubernetes_hash",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "important_configuration_files_hash ~ '^[0-9a-f]{64}$'",
            name="ck_repository_snapshots_configuration_hash",
        ).ddl_if(dialect="postgresql"),
    )


class ChangeAnalysis(Base):
    """Deterministic source-diff classification used to decide analysis reuse."""

    __tablename__ = "change_analyses"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    deployment_id = Column(UUID(as_uuid=True), ForeignKey("deployments.id", ondelete="SET NULL"), nullable=True)
    pipeline_run_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id", ondelete="SET NULL"), nullable=True)
    baseline_snapshot_id = Column(
        UUID(as_uuid=True),
        ForeignKey("repository_analysis_snapshots.id", ondelete="SET NULL"),
        nullable=True,
    )
    idempotency_key = Column(String(128), nullable=False)
    baseline_revision = Column(String(64), nullable=True)
    target_revision = Column(String(64), nullable=False)
    changed_paths_digest = Column(String(64), nullable=False)
    change_fingerprint = Column(String(64), nullable=False)
    classifier_version = Column(String(64), nullable=False)
    status = Column(String(16), nullable=False, default=ExecutionStatus.queued.value)
    changed_file_count = Column(Integer, nullable=False, default=0)
    application_source_changed = Column(Boolean, nullable=False, default=False)
    dependencies_changed = Column(Boolean, nullable=False, default=False)
    deployment_config_changed = Column(Boolean, nullable=False, default=False)
    infrastructure_changed = Column(Boolean, nullable=False, default=False)
    kubernetes_changed = Column(Boolean, nullable=False, default=False)
    security_policy_changed = Column(Boolean, nullable=False, default=False)
    architecture_changed = Column(Boolean, nullable=False, default=False)
    documentation_only = Column(Boolean, nullable=False, default=False)
    deployment_relevant = Column(Boolean, nullable=False, default=False)
    repository_ai_required = Column(Boolean, nullable=False, default=False)
    decision_reason = Column(Text, nullable=False)
    category_counts = Column(POSTGRES_JSON, nullable=False, default=dict)
    sampled_paths = Column(POSTGRES_JSON, nullable=False, default=list)
    error_code = Column(String(64), nullable=True)
    redacted_error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    tenant = relationship("Tenant")
    project = relationship("Project")
    deployment = relationship("Deployment")
    pipeline_run = relationship("PipelineRun")
    baseline_snapshot = relationship("RepositoryAnalysisSnapshot")

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_change_analyses_tenant_idempotency"),
        Index("ix_change_analyses_project_created", "project_id", "created_at"),
        Index("ix_change_analyses_pipeline_run_id", "pipeline_run_id"),
        Index(
            "ix_change_analyses_target_fingerprint",
            "tenant_id",
            "project_id",
            "target_revision",
            "change_fingerprint",
        ),
        CheckConstraint("changed_file_count >= 0", name="ck_change_analyses_file_count"),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'skipped', "
            "'blocked', 'unavailable', 'cancelled')",
            name="ck_change_analyses_status",
        ),
        CheckConstraint(
            "changed_paths_digest ~ '^[0-9a-f]{64}$'",
            name="ck_change_analyses_paths_digest",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "change_fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_change_analyses_fingerprint",
        ).ddl_if(dialect="postgresql"),
    )


class SecurityScan(Base):
    """One deterministic scanner invocation and its policy outcome."""

    __tablename__ = "security_scans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    deployment_id = Column(UUID(as_uuid=True), ForeignKey("deployments.id", ondelete="SET NULL"), nullable=True)
    pipeline_run_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id", ondelete="SET NULL"), nullable=True)
    stage_attempt_id = Column(
        UUID(as_uuid=True),
        ForeignKey("pipeline_stage_attempts.id", ondelete="SET NULL"),
        nullable=True,
    )
    result_artifact_id = Column(UUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True)
    idempotency_key = Column(String(128), nullable=False)
    scan_type = Column(String(32), nullable=False)
    status = Column(String(16), nullable=False, default=ExecutionStatus.queued.value)
    policy_status = Column(String(16), nullable=False, default="pending")
    blocking_enabled = Column(Boolean, nullable=False, default=True)
    tool_name = Column(String(128), nullable=False)
    tool_version = Column(String(128), nullable=True)
    target_kind = Column(String(32), nullable=False)
    target_revision = Column(String(128), nullable=True)
    target_digest = Column(String(64), nullable=True)
    finding_count = Column(Integer, nullable=False, default=0)
    critical_count = Column(Integer, nullable=False, default=0)
    high_count = Column(Integer, nullable=False, default=0)
    medium_count = Column(Integer, nullable=False, default=0)
    low_count = Column(Integer, nullable=False, default=0)
    info_count = Column(Integer, nullable=False, default=0)
    result_digest = Column(String(64), nullable=True)
    error_code = Column(String(64), nullable=True)
    redacted_error = Column(Text, nullable=True)
    summary = Column(POSTGRES_JSON, nullable=False, default=dict)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)

    tenant = relationship("Tenant")
    project = relationship("Project")
    deployment = relationship("Deployment")
    pipeline_run = relationship("PipelineRun")
    stage_attempt = relationship("PipelineStageAttempt")
    result_artifact = relationship("Artifact")
    findings = relationship(
        "SecurityFinding",
        back_populates="security_scan",
        cascade="all, delete-orphan",
        order_by="SecurityFinding.created_at",
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_security_scans_tenant_idempotency"),
        Index("ix_security_scans_project_created", "project_id", "created_at"),
        Index("ix_security_scans_pipeline_type", "pipeline_run_id", "scan_type"),
        Index("ix_security_scans_status", "status"),
        CheckConstraint(
            "scan_type IN ('sast', 'dependency', 'secret', 'container', 'iac', "
            "'kubernetes', 'sbom')",
            name="ck_security_scans_type",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'skipped', "
            "'blocked', 'unavailable', 'cancelled')",
            name="ck_security_scans_status",
        ),
        CheckConstraint(
            "policy_status IN ('pending', 'passed', 'warning', 'blocked', 'unavailable')",
            name="ck_security_scans_policy_status",
        ),
        CheckConstraint(
            "finding_count >= 0 AND critical_count >= 0 AND high_count >= 0 "
            "AND medium_count >= 0 AND low_count >= 0 AND info_count >= 0",
            name="ck_security_scans_counts",
        ),
        CheckConstraint(
            "target_digest IS NULL OR target_digest ~ '^[0-9a-f]{64}$'",
            name="ck_security_scans_target_digest",
        ).ddl_if(dialect="postgresql"),
        CheckConstraint(
            "result_digest IS NULL OR result_digest ~ '^[0-9a-f]{64}$'",
            name="ck_security_scans_result_digest",
        ).ddl_if(dialect="postgresql"),
    )


class SecurityFinding(Base):
    """A deduplicated finding; secret evidence must remain masked or hashed."""

    __tablename__ = "security_findings"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    deployment_id = Column(UUID(as_uuid=True), ForeignKey("deployments.id", ondelete="SET NULL"), nullable=True)
    security_scan_id = Column(UUID(as_uuid=True), ForeignKey("security_scans.id", ondelete="CASCADE"), nullable=False)
    fingerprint = Column(String(64), nullable=False)
    rule_id = Column(String(256), nullable=False)
    category = Column(String(64), nullable=False)
    severity = Column(String(16), nullable=False)
    status = Column(String(16), nullable=False, default="open")
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=True)
    remediation = Column(Text, nullable=True)
    location_path = Column(Text, nullable=True)
    line_start = Column(Integer, nullable=True)
    line_end = Column(Integer, nullable=True)
    package_name = Column(Text, nullable=True)
    package_version = Column(Text, nullable=True)
    fixed_version = Column(Text, nullable=True)
    is_blocking = Column(Boolean, nullable=False, default=False)
    masked_evidence = Column(Text, nullable=True)
    evidence = Column(POSTGRES_JSON, nullable=False, default=dict)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)
    resolved_at = Column(DateTime(timezone=True), nullable=True)

    tenant = relationship("Tenant")
    project = relationship("Project")
    deployment = relationship("Deployment")
    security_scan = relationship("SecurityScan", back_populates="findings")

    __table_args__ = (
        UniqueConstraint("security_scan_id", "fingerprint", name="uq_security_findings_scan_fingerprint"),
        Index("ix_security_findings_project_severity", "project_id", "severity"),
        Index("ix_security_findings_scan_id", "security_scan_id"),
        CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low', 'info')",
            name="ck_security_findings_severity",
        ),
        CheckConstraint(
            "status IN ('open', 'accepted_risk', 'resolved', 'false_positive')",
            name="ck_security_findings_status",
        ),
        CheckConstraint(
            "line_start IS NULL OR line_start >= 1",
            name="ck_security_findings_line_start",
        ),
        CheckConstraint(
            "line_end IS NULL OR (line_start IS NOT NULL AND line_end >= line_start)",
            name="ck_security_findings_line_end",
        ),
        CheckConstraint(
            "fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_security_findings_fingerprint",
        ).ddl_if(dialect="postgresql"),
    )


class WebhookDelivery(Base):
    """Digest-only GitHub delivery record; raw payloads/signatures are not stored."""

    __tablename__ = "webhook_deliveries"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    deployment_id = Column(UUID(as_uuid=True), ForeignKey("deployments.id", ondelete="SET NULL"), nullable=True)
    pipeline_run_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id", ondelete="SET NULL"), nullable=True)
    provider = Column(String(32), nullable=False, default="github")
    external_delivery_id = Column(String(128), nullable=False)
    event_type = Column(String(64), nullable=False)
    event_action = Column(String(64), nullable=True)
    signature_status = Column(String(16), nullable=False, default="unverified")
    status = Column(String(16), nullable=False, default=ExecutionStatus.queued.value)
    repository_external_id = Column(String(128), nullable=True)
    branch = Column(Text, nullable=True)
    source_revision = Column(String(64), nullable=True)
    payload_digest = Column(String(64), nullable=False)
    attempt_count = Column(Integer, nullable=False, default=0)
    failure_code = Column(String(64), nullable=True)
    redacted_error = Column(Text, nullable=True)
    received_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    validated_at = Column(DateTime(timezone=True), nullable=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    tenant = relationship("Tenant")
    project = relationship("Project")
    deployment = relationship("Deployment")
    pipeline_run = relationship("PipelineRun")

    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "provider",
            "external_delivery_id",
            name="uq_webhook_deliveries_provider_delivery",
        ),
        Index("ix_webhook_deliveries_project_received", "project_id", "received_at"),
        Index("ix_webhook_deliveries_status", "status"),
        CheckConstraint(
            "signature_status IN ('unverified', 'verified', 'invalid', 'unavailable')",
            name="ck_webhook_deliveries_signature_status",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'skipped', "
            "'blocked', 'unavailable', 'cancelled')",
            name="ck_webhook_deliveries_status",
        ),
        CheckConstraint("attempt_count >= 0", name="ck_webhook_deliveries_attempt_count"),
        CheckConstraint(
            "payload_digest ~ '^[0-9a-f]{64}$'",
            name="ck_webhook_deliveries_payload_digest",
        ).ddl_if(dialect="postgresql"),
    )


class Incident(Base):
    """A durable anomaly or deployment incident with an explicit lifecycle."""

    __tablename__ = "incidents"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    deployment_id = Column(UUID(as_uuid=True), ForeignKey("deployments.id", ondelete="SET NULL"), nullable=True)
    pipeline_run_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id", ondelete="SET NULL"), nullable=True)
    stage_attempt_id = Column(
        UUID(as_uuid=True),
        ForeignKey("pipeline_stage_attempts.id", ondelete="SET NULL"),
        nullable=True,
    )
    acknowledged_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    resolved_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    idempotency_key = Column(String(128), nullable=False)
    status = Column(String(16), nullable=False, default="open")
    severity = Column(String(16), nullable=False)
    detection_source = Column(String(64), nullable=False)
    rule_key = Column(String(128), nullable=False)
    title = Column(Text, nullable=False)
    redacted_summary = Column(Text, nullable=False)
    evidence = Column(POSTGRES_JSON, nullable=False, default=list)
    first_observed_at = Column(DateTime(timezone=True), nullable=False)
    last_observed_at = Column(DateTime(timezone=True), nullable=False)
    acknowledged_at = Column(DateTime(timezone=True), nullable=True)
    mitigated_at = Column(DateTime(timezone=True), nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    tenant = relationship("Tenant")
    project = relationship("Project")
    deployment = relationship("Deployment")
    pipeline_run = relationship("PipelineRun")
    stage_attempt = relationship("PipelineStageAttempt")
    acknowledged_by_user = relationship("User", foreign_keys=[acknowledged_by_user_id])
    resolved_by_user = relationship("User", foreign_keys=[resolved_by_user_id])

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_incidents_tenant_idempotency"),
        Index("ix_incidents_project_status", "project_id", "status"),
        Index("ix_incidents_deployment_id", "deployment_id"),
        Index("ix_incidents_last_observed", "tenant_id", "last_observed_at"),
        CheckConstraint(
            "status IN ('open', 'investigating', 'mitigated', 'resolved', 'dismissed')",
            name="ck_incidents_status",
        ),
        CheckConstraint(
            "severity IN ('critical', 'high', 'medium', 'low', 'info')",
            name="ck_incidents_severity",
        ),
        CheckConstraint("last_observed_at >= first_observed_at", name="ck_incidents_observed_order"),
    )


class AIInvestigation(Base):
    """Structured, provenance-bearing diagnosis over redacted evidence only."""

    __tablename__ = "ai_investigations"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    deployment_id = Column(UUID(as_uuid=True), ForeignKey("deployments.id", ondelete="SET NULL"), nullable=True)
    pipeline_run_id = Column(UUID(as_uuid=True), ForeignKey("pipeline_runs.id", ondelete="SET NULL"), nullable=True)
    stage_attempt_id = Column(
        UUID(as_uuid=True),
        ForeignKey("pipeline_stage_attempts.id", ondelete="SET NULL"),
        nullable=True,
    )
    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True)
    requested_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    idempotency_key = Column(String(128), nullable=False)
    trigger_type = Column(String(32), nullable=False)
    failed_stage_key = Column(String(64), nullable=True)
    status = Column(String(16), nullable=False, default=ExecutionStatus.queued.value)
    model_provider = Column(String(64), nullable=False)
    model_name = Column(String(128), nullable=False)
    model_version = Column(String(128), nullable=True)
    prompt_version = Column(String(64), nullable=False)
    evidence_digest = Column(String(64), nullable=False)
    evidence = Column(POSTGRES_JSON, nullable=False, default=list)
    failure_summary = Column(Text, nullable=True)
    root_cause = Column(Text, nullable=True)
    severity = Column(String(16), nullable=True)
    recommended_fix = Column(Text, nullable=True)
    resolution_steps = Column(POSTGRES_JSON, nullable=False, default=list)
    confidence = Column(Integer, nullable=True)
    safe_action_available = Column(Boolean, nullable=False, default=False)
    requires_user_action = Column(Boolean, nullable=False, default=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    model_cost_microusd = Column(BigInteger, nullable=True)
    error_code = Column(String(64), nullable=True)
    redacted_error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    tenant = relationship("Tenant")
    project = relationship("Project")
    deployment = relationship("Deployment")
    pipeline_run = relationship("PipelineRun")
    stage_attempt = relationship("PipelineStageAttempt")
    incident = relationship("Incident")
    requested_by_user = relationship("User")

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_ai_investigations_tenant_idempotency"),
        Index("ix_ai_investigations_project_created", "project_id", "created_at"),
        Index("ix_ai_investigations_incident_id", "incident_id"),
        Index("ix_ai_investigations_pipeline_run_id", "pipeline_run_id"),
        CheckConstraint(
            "trigger_type IN ('pipeline_failure', 'security_failure', 'terraform_failure', "
            "'test_failure', 'incident', 'architecture_change', 'manual')",
            name="ck_ai_investigations_trigger_type",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'skipped', "
            "'blocked', 'unavailable', 'cancelled')",
            name="ck_ai_investigations_status",
        ),
        CheckConstraint(
            "severity IS NULL OR severity IN ('critical', 'high', 'medium', 'low', 'info')",
            name="ck_ai_investigations_severity",
        ),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 100)",
            name="ck_ai_investigations_confidence",
        ),
        CheckConstraint(
            "evidence_digest ~ '^[0-9a-f]{64}$'",
            name="ck_ai_investigations_evidence_digest",
        ).ddl_if(dialect="postgresql"),
    )


class RemediationProposal(Base):
    """A redacted, risk-classified action proposal that cannot self-authorize."""

    __tablename__ = "remediation_proposals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    deployment_id = Column(UUID(as_uuid=True), ForeignKey("deployments.id", ondelete="SET NULL"), nullable=True)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True)
    investigation_id = Column(UUID(as_uuid=True), ForeignKey("ai_investigations.id", ondelete="SET NULL"), nullable=True)
    parameter_artifact_id = Column(UUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True)
    proposed_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    decided_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    idempotency_key = Column(String(128), nullable=False)
    action_type = Column(String(128), nullable=False)
    title = Column(Text, nullable=False)
    description = Column(Text, nullable=False)
    risk_tier = Column(String(16), nullable=False)
    status = Column(String(24), nullable=False, default="proposed")
    approval_required = Column(Boolean, nullable=False, default=True)
    parameter_digest = Column(String(64), nullable=False)
    redacted_parameters = Column(POSTGRES_JSON, nullable=False, default=dict)
    rationale = Column(Text, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    decided_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    tenant = relationship("Tenant")
    project = relationship("Project")
    deployment = relationship("Deployment")
    incident = relationship("Incident")
    investigation = relationship("AIInvestigation")
    parameter_artifact = relationship("Artifact")
    proposed_by_user = relationship("User", foreign_keys=[proposed_by_user_id])
    decided_by_user = relationship("User", foreign_keys=[decided_by_user_id])

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_remediation_proposals_tenant_idempotency"),
        Index("ix_remediation_proposals_project_status", "project_id", "status"),
        Index("ix_remediation_proposals_incident_id", "incident_id"),
        CheckConstraint("risk_tier IN ('low', 'medium', 'high')", name="ck_remediation_proposals_risk_tier"),
        CheckConstraint(
            "status IN ('proposed', 'pending_approval', 'approved', 'denied', "
            "'expired', 'cancelled', 'executed')",
            name="ck_remediation_proposals_status",
        ),
        CheckConstraint(
            "risk_tier <> 'high' OR approval_required",
            name="ck_remediation_proposals_high_risk_approval",
        ),
        CheckConstraint(
            "status NOT IN ('approved', 'denied') OR "
            "(decided_by_user_id IS NOT NULL AND decided_at IS NOT NULL)",
            name="ck_remediation_proposals_decision_actor",
        ),
        CheckConstraint(
            "parameter_digest ~ '^[0-9a-f]{64}$'",
            name="ck_remediation_proposals_parameter_digest",
        ).ddl_if(dialect="postgresql"),
    )


class RemediationExecution(Base):
    """An idempotent execution attempt for an authorized remediation proposal."""

    __tablename__ = "remediation_executions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    tenant_id = Column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False)
    deployment_id = Column(UUID(as_uuid=True), ForeignKey("deployments.id", ondelete="SET NULL"), nullable=True)
    incident_id = Column(UUID(as_uuid=True), ForeignKey("incidents.id", ondelete="SET NULL"), nullable=True)
    proposal_id = Column(
        UUID(as_uuid=True),
        ForeignKey("remediation_proposals.id", ondelete="CASCADE"),
        nullable=False,
    )
    requested_by_user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    result_artifact_id = Column(UUID(as_uuid=True), ForeignKey("artifacts.id", ondelete="SET NULL"), nullable=True)
    idempotency_key = Column(String(128), nullable=False)
    attempt_number = Column(Integer, nullable=False, default=1)
    executor_kind = Column(String(32), nullable=False)
    executor_name = Column(String(128), nullable=False)
    status = Column(String(16), nullable=False, default=ExecutionStatus.queued.value)
    verification_status = Column(String(16), nullable=False, default=ExecutionStatus.queued.value)
    result_summary = Column(Text, nullable=True)
    evidence = Column(POSTGRES_JSON, nullable=False, default=list)
    failure_code = Column(String(64), nullable=True)
    redacted_error = Column(Text, nullable=True)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)
    verified_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)

    tenant = relationship("Tenant")
    project = relationship("Project")
    deployment = relationship("Deployment")
    incident = relationship("Incident")
    proposal = relationship("RemediationProposal")
    requested_by_user = relationship("User")
    result_artifact = relationship("Artifact")

    __table_args__ = (
        UniqueConstraint("tenant_id", "idempotency_key", name="uq_remediation_executions_tenant_idempotency"),
        UniqueConstraint("proposal_id", "attempt_number", name="uq_remediation_executions_proposal_attempt"),
        Index("ix_remediation_executions_project_status", "project_id", "status"),
        Index("ix_remediation_executions_incident_id", "incident_id"),
        CheckConstraint("attempt_number >= 1", name="ck_remediation_executions_attempt_number"),
        CheckConstraint(
            "executor_kind IN ('deterministic', 'operator', 'automation')",
            name="ck_remediation_executions_executor_kind",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'succeeded', 'failed', 'skipped', "
            "'blocked', 'unavailable', 'cancelled')",
            name="ck_remediation_executions_status",
        ),
        CheckConstraint(
            "verification_status IN ('queued', 'running', 'succeeded', 'failed', 'skipped', "
            "'blocked', 'unavailable', 'cancelled')",
            name="ck_remediation_executions_verification_status",
        ),
    )

