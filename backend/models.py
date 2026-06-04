import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, DateTime, Text, Integer, Float, Boolean,
    ForeignKey, JSON, Enum as SAEnum, Index
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, declarative_base
import enum

Base = declarative_base()


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
    api_key = Column(Text, nullable=True, unique=True)
    refresh_token = Column(Text, nullable=True)

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
    activity_events = relationship("ActivityEvent", back_populates="user", cascade="all, delete-orphan")
    deployment_recommendations = relationship("DeploymentRecommendation", back_populates="user", cascade="all, delete-orphan")
    failure_analyses = relationship("FailureAnalysis", back_populates="user", cascade="all, delete-orphan")
    azure_connections = relationship("UserAzureConnection", back_populates="user", cascade="all, delete-orphan")
    billing_operations = relationship("BillingOperation", back_populates="user", cascade="all, delete-orphan")
    code_uploads = relationship("CodeUpload", back_populates="user", cascade="all, delete-orphan")

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
        }


# ──────────────────────────────────────────────
# PROJECTS (connected repos / apps)
# ──────────────────────────────────────────────

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
    activity_events = relationship("ActivityEvent", back_populates="project", cascade="all, delete-orphan")
    deployment_recommendations = relationship("DeploymentRecommendation", back_populates="project", cascade="all, delete-orphan")
    failure_analyses = relationship("FailureAnalysis", back_populates="project", cascade="all, delete-orphan")
    databases = relationship("DatabaseInstance", back_populates="project", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_projects_user_id", "user_id"),
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
    predictive_scaling = Column(Boolean, default=True)
    auto_rollback = Column(Boolean, default=True)
    ai_threat_mitigation = Column(Boolean, default=True)
    auto_oom_restart = Column(Boolean, default=True)
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
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    project_id = Column(UUID(as_uuid=True), ForeignKey("projects.id", ondelete="SET NULL"), nullable=True)
    action = Column(Text, nullable=False)
    details = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    # Relationships
    user = relationship("User", back_populates="activity_events")
    project = relationship("Project", back_populates="activity_events")

    __table_args__ = (
        Index("ix_activity_events_user_id", "user_id"),
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
# DEPLOYMENT RECOMMENDATIONS
# ──────────────────────────────────────────────

class UserAzureConnection(Base):
    __tablename__ = "user_azure_connections"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    tenant_id = Column(Text, nullable=False)
    subscription_id = Column(Text, nullable=False)
    client_id = Column(Text, nullable=True)
    client_secret_encrypted = Column(Text, nullable=True)
    region = Column(Text, default="eastus")
    resource_group = Column(Text, nullable=True)
    acr_login_server = Column(Text, nullable=True)
    aks_cluster_name = Column(Text, nullable=True)
    namespace_prefix = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", back_populates="azure_connections")

    __table_args__ = (
        Index("ix_user_azure_connections_user_id", "user_id"),
    )


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
    confidence = Column(Integer, default=95)
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
