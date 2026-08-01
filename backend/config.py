"""Application configuration loaded from Azure Key Vault.

Only ``APP_ENV`` and ``AZURE_KEYVAULT_URL`` remain process settings: the first
selects the startup policy and the second is required to locate Key Vault. All
application configuration, including non-secret operational values, is read
from Key Vault using the ``zeroops-<kebab-case-setting-name>`` convention.
"""

from __future__ import annotations

import os
import secrets
import subprocess

try:
    from backend.services import vault
except ImportError:  # Allows ``uvicorn main:app`` from the backend directory.
    from services import vault


def _setting(name: str, default: str = "") -> str:
    return vault.get_application_setting(
        name,
        default=default,
        # Required settings are validated explicitly after all optional
        # integrations are loaded. This keeps optional providers optional.
        required=False,
    )


def _integer(name: str, default: int) -> int:
    value = _setting(name, str(default)).strip()
    try:
        return int(value)
    except ValueError as error:
        raise RuntimeError(f"{name} must be an integer in Azure Key Vault.") from error


def _boolean(name: str, default: bool) -> bool:
    value = _setting(name, str(default).lower()).strip().lower()
    if value in {"true", "1", "yes", "on"}:
        return True
    if value in {"false", "0", "no", "off"}:
        return False
    raise RuntimeError(f"{name} must be a boolean in Azure Key Vault.")


def _parse_csv(name: str, default_values: list[str]) -> list[str]:
    raw = _setting(name, "")
    if not raw:
        return default_values.copy()
    parsed = [item.strip() for item in raw.split(",") if item.strip()]
    if "*" in parsed:
        parsed = [item for item in parsed if item != "*"]
        for value in default_values:
            if value not in parsed:
                parsed.append(value)
    return parsed


# Bootstrap settings. APP_ENV is deliberately not read from Key Vault because
# the application must know whether to fail closed before loading its config.
# It is mandatory and exact so an omitted or misspelled production setting
# cannot silently select permissive development behavior.
APP_ENV = os.environ.get("APP_ENV", "")
if APP_ENV not in {"development", "test", "production"}:
    raise RuntimeError("APP_ENV must be explicitly set to development, test, or production.")
IS_PRODUCTION = APP_ENV == "production"
AZURE_KEYVAULT_URL = vault.AZURE_KEYVAULT_URL

if IS_PRODUCTION and not AZURE_KEYVAULT_URL:
    raise RuntimeError("AZURE_KEYVAULT_URL must be configured when APP_ENV=production.")

# Server settings
PORT = _integer("PORT", 8000)
HOST = _setting("HOST", "0.0.0.0")

# Browser and cross-origin configuration
FRONTEND_ORIGIN = _setting("FRONTEND_ORIGIN", "").rstrip("/")
FRONTEND_URL = _setting("FRONTEND_URL", FRONTEND_ORIGIN).rstrip("/")
if not FRONTEND_URL and not IS_PRODUCTION:
    FRONTEND_URL = "http://localhost:3000"
ZEROOPS_BACKEND_URL = _setting("ZEROOPS_BACKEND_URL", "").rstrip("/")

DEFAULT_ALLOWED_ORIGINS = [FRONTEND_URL] if FRONTEND_URL else []
if not IS_PRODUCTION:
    DEFAULT_ALLOWED_ORIGINS.extend(["http://localhost:3000", "http://127.0.0.1:3000"])

CORS_ORIGINS = _parse_csv("CORS_ORIGINS", DEFAULT_ALLOWED_ORIGINS)
for url in [FRONTEND_ORIGIN, FRONTEND_URL]:
    if url and url not in CORS_ORIGINS:
        CORS_ORIGINS.append(url)
CORS_ORIGINS = list(dict.fromkeys(CORS_ORIGINS))
ALLOWED_HOSTS = _parse_csv("ALLOWED_HOSTS", ["*"] if not IS_PRODUCTION else [])
ALLOW_CREDENTIALS = True

# AI providers
OPENAI_API_KEY = _setting("OPENAI_API_KEY")
OPENAI_MODEL = _setting("OPENAI_MODEL", "gpt-5.4-mini")
AI_MODEL_TIMEOUT_SECONDS = _integer("AI_MODEL_TIMEOUT_SECONDS", 30)
GITHUB_MODELS_API_KEY = _setting("GITHUB_MODELS_API_KEY")
GITHUB_MODELS_ENDPOINT = _setting("GITHUB_MODELS_ENDPOINT", "https://models.github.ai/inference")
GITHUB_MODELS_MODEL = _setting("GITHUB_MODELS_MODEL", "openai/gpt-4o")
NVIDIA_API_KEY = _setting("NVIDIA_API_KEY")
NVIDIA_ENDPOINT = _setting("NVIDIA_ENDPOINT", "https://integrate.api.nvidia.com/v1")
NVIDIA_MODEL = _setting("NVIDIA_MODEL", "z-ai/glm-5.2")

# Isolated AI workload routes. These settings deliberately do not inherit from
# NVIDIA_API_KEY, GITHUB_MODELS_API_KEY, or OPENAI_API_KEY. Repository analysis
# may degrade to the deterministic scanner when its route is unavailable, while
# Terraform generation fails closed. In production each route is loaded by its
# own managed workload identity from its dedicated Key Vault.
AI_GITHUB_API_VERSION = _setting("AI_GITHUB_API_VERSION", "2026-03-10")

# Repository analysis workload. Defaults to NVIDIA for the testing prototype;
# override via Key Vault for production routes.
AI_REPOSITORY_PROVIDER = _setting("AI_REPOSITORY_PROVIDER", "nvidia").strip().lower()
AI_REPOSITORY_API_KEY = _setting("AI_REPOSITORY_API_KEY")
AI_REPOSITORY_ENDPOINT = _setting(
    "AI_REPOSITORY_ENDPOINT",
    "https://integrate.api.nvidia.com/v1",
).rstrip("/")
AI_REPOSITORY_MODEL = _setting("AI_REPOSITORY_MODEL", "z-ai/glm-5.2")
AI_REPOSITORY_AGENT_NAME = _setting("AI_REPOSITORY_AGENT_NAME")
AI_REPOSITORY_PROMPT_VERSION = _setting("AI_REPOSITORY_PROMPT_VERSION", "repository-analysis.v1")
AI_REPOSITORY_MAX_INPUT_CHARS = _integer("AI_REPOSITORY_MAX_INPUT_CHARS", 40_000)
AI_REPOSITORY_MAX_OUTPUT_TOKENS = _integer("AI_REPOSITORY_MAX_OUTPUT_TOKENS", 1_600)

# Terraform generation workload. Defaults to NVIDIA for the testing prototype;
# override via Key Vault for production routes.
AI_TERRAFORM_PROVIDER = _setting("AI_TERRAFORM_PROVIDER", "nvidia").strip().lower()
AI_TERRAFORM_API_KEY = _setting("AI_TERRAFORM_API_KEY")
AI_TERRAFORM_ENDPOINT = _setting(
    "AI_TERRAFORM_ENDPOINT",
    "https://integrate.api.nvidia.com/v1",
).rstrip("/")
AI_TERRAFORM_MODEL = _setting("AI_TERRAFORM_MODEL", "z-ai/glm-5.2")
AI_TERRAFORM_AGENT_NAME = _setting("AI_TERRAFORM_AGENT_NAME")
AI_TERRAFORM_PROMPT_VERSION = _setting("AI_TERRAFORM_PROMPT_VERSION", "terraform-generation.v1")
AI_TERRAFORM_MAX_INPUT_CHARS = _integer("AI_TERRAFORM_MAX_INPUT_CHARS", 40_000)
AI_TERRAFORM_MAX_OUTPUT_TOKENS = _integer("AI_TERRAFORM_MAX_OUTPUT_TOKENS", 4_000)

# OAuth and session security
GITHUB_TOKEN = _setting("GITHUB_TOKEN")
GITHUB_CLIENT_ID = _setting("GITHUB_CLIENT_ID")
GITHUB_CLIENT_SECRET = _setting("GITHUB_CLIENT_SECRET")
GITHUB_OAUTH_SCOPES = _setting("GITHUB_OAUTH_SCOPES", "repo,read:user,user:email")
GOOGLE_CLIENT_ID = _setting("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET = _setting("GOOGLE_CLIENT_SECRET")
GOOGLE_OAUTH_SCOPES = _setting("GOOGLE_OAUTH_SCOPES", "openid email profile")
MFA_ENCRYPTION_KEY = _setting("MFA_ENCRYPTION_KEY")
MFA_ISSUER = _setting("MFA_ISSUER", "ZeroOps AI")
MFA_CHALLENGE_EXPIRE_MINUTES = _integer("MFA_CHALLENGE_EXPIRE_MINUTES", 5)
MFA_REAUTH_WINDOW_MINUTES = _integer("MFA_REAUTH_WINDOW_MINUTES", 10)
DATABASE_URL = _setting("DATABASE_URL")
JWT_SECRET = _setting("JWT_SECRET")
JWT_ALGORITHM = _setting("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = _integer("ACCESS_TOKEN_EXPIRE_MINUTES", 15)
REFRESH_TOKEN_EXPIRE_DAYS = _integer("REFRESH_TOKEN_EXPIRE_DAYS", 7)
WORKER_EVENT_TOKEN = _setting("WORKER_EVENT_TOKEN")

# Email and phone verification
SMTP_HOST = _setting("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = _integer("SMTP_PORT", 587)
SMTP_USERNAME = _setting("SMTP_USERNAME")
SMTP_PASSWORD = _setting("SMTP_PASSWORD")
SMTP_FROM_EMAIL = _setting("SMTP_FROM_EMAIL")
SMTP_USE_TLS = _boolean("SMTP_USE_TLS", True)
EMAIL_VERIFICATION_EXPIRE_HOURS = _integer("EMAIL_VERIFICATION_EXPIRE_HOURS", 24)
EMAIL_OTP_EXPIRE_MINUTES = _integer("EMAIL_OTP_EXPIRE_MINUTES", 10)
EMAIL_OTP_LENGTH = _integer("EMAIL_OTP_LENGTH", 6)
PHONE_VERIFICATION_REQUIRED = _boolean("PHONE_VERIFICATION_REQUIRED", True)
TWILIO_ACCOUNT_SID = _setting("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = _setting("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = _setting("TWILIO_FROM_NUMBER")
PHONE_OTP_EXPIRE_MINUTES = _integer("PHONE_OTP_EXPIRE_MINUTES", 5)
PHONE_OTP_LENGTH = _integer("PHONE_OTP_LENGTH", 6)
PHONE_OTP_MAX_ATTEMPTS = _integer("PHONE_OTP_MAX_ATTEMPTS", 5)
PHONE_OTP_RESEND_COOLDOWN_SECONDS = _integer("PHONE_OTP_RESEND_COOLDOWN_SECONDS", 60)
LOGIN_MAX_FAILURES = _integer("LOGIN_MAX_FAILURES", 10)
LOGIN_LOCKOUT_MINUTES = _integer("LOGIN_LOCKOUT_MINUTES", 15)

# Azure operations and product controls
AZURE_DEFAULT_REGION = _setting("AZURE_DEFAULT_REGION", "eastus")
ZEROOPS_PUBLIC_BASE_DOMAIN = _setting("ZEROOPS_PUBLIC_BASE_DOMAIN", "").strip().strip(".")
ARTIFACT_STORAGE_ACCOUNT_URL = _setting("ARTIFACT_STORAGE_ACCOUNT_URL", "").rstrip("/")
ARTIFACT_STORAGE_MANAGED_IDENTITY_CLIENT_ID = _setting(
    "ARTIFACT_STORAGE_MANAGED_IDENTITY_CLIENT_ID",
    "",
)
ARTIFACT_STORAGE_NAMESPACE_KEY = _setting("ARTIFACT_STORAGE_NAMESPACE_KEY", "")
ARTIFACT_STORAGE_MAX_DOWNLOAD_MB = _integer("ARTIFACT_STORAGE_MAX_DOWNLOAD_MB", 25)
RISK_COST_THRESHOLD_CENTS = _integer("RISK_COST_THRESHOLD_CENTS", 5000)
MAINTENANCE_WINDOW_UTC = _setting("MAINTENANCE_WINDOW_UTC", "")
PAYMENT_PROVIDER = _setting("PAYMENT_PROVIDER", "manual")
AI_PAID_OPERATION_PRICE_CENTS = _integer("AI_PAID_OPERATION_PRICE_CENTS", 499)
AI_FREE_DAILY_LIMIT = _integer("AI_FREE_DAILY_LIMIT", 5)
STRIPE_SECRET_KEY = _setting("STRIPE_SECRET_KEY")
STRIPE_WEBHOOK_SECRET = _setting("STRIPE_WEBHOOK_SECRET")
MAX_CODE_UPLOAD_MB = _integer("MAX_CODE_UPLOAD_MB", 50)
MAX_UPLOAD_ARCHIVE_FILES = _integer("MAX_UPLOAD_ARCHIVE_FILES", 10000)
MAX_UPLOAD_UNCOMPRESSED_MB = _integer("MAX_UPLOAD_UNCOMPRESSED_MB", 250)
MAX_UPLOAD_COMPRESSION_RATIO = _integer("MAX_UPLOAD_COMPRESSION_RATIO", 100)
MAX_RATE_LIMIT_KEYS = _integer("MAX_RATE_LIMIT_KEYS", 10000)
DB_SSL_ENABLED = _boolean("DB_SSL_ENABLED", True)
DB_SSL_VERIFY = _boolean("DB_SSL_VERIFY", True)
DB_SSL_ROOT_CERT = _setting("DB_SSL_ROOT_CERT", "")
WORKER_POLL_INTERVAL_SECONDS = _integer("WORKER_POLL_INTERVAL_SECONDS", 5)
WORKER_LEASE_SECONDS = _integer("WORKER_LEASE_SECONDS", 180)
WORKER_HEARTBEAT_SECONDS = _integer("WORKER_HEARTBEAT_SECONDS", 30)
WORKER_MAX_ATTEMPTS = _integer("WORKER_MAX_ATTEMPTS", 3)
WORKER_RECOVERY_BATCH_SIZE = _integer("WORKER_RECOVERY_BATCH_SIZE", 25)
WORKER_HEALTH_PORT = _integer("WORKER_HEALTH_PORT", 8085)

if WORKER_POLL_INTERVAL_SECONDS < 1:
    raise RuntimeError("WORKER_POLL_INTERVAL_SECONDS must be at least 1.")
if not 1 <= ARTIFACT_STORAGE_MAX_DOWNLOAD_MB <= 250:
    raise RuntimeError("ARTIFACT_STORAGE_MAX_DOWNLOAD_MB must be between 1 and 250.")
if WORKER_LEASE_SECONDS < 30:
    raise RuntimeError("WORKER_LEASE_SECONDS must be at least 30.")
if not 1 <= WORKER_HEARTBEAT_SECONDS < WORKER_LEASE_SECONDS:
    raise RuntimeError("WORKER_HEARTBEAT_SECONDS must be positive and shorter than WORKER_LEASE_SECONDS.")
if not 1 <= WORKER_MAX_ATTEMPTS <= 10:
    raise RuntimeError("WORKER_MAX_ATTEMPTS must be between 1 and 10.")
if not 1 <= WORKER_RECOVERY_BATCH_SIZE <= 100:
    raise RuntimeError("WORKER_RECOVERY_BATCH_SIZE must be between 1 and 100.")
if not 1024 <= WORKER_HEALTH_PORT <= 65535:
    raise RuntimeError("WORKER_HEALTH_PORT must be between 1024 and 65535.")

WORKSPACE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "workspace"))
os.makedirs(WORKSPACE_DIR, exist_ok=True)
AZURE_CLI_PATH = _setting("AZURE_CLI_PATH", "az")


def check_azure_cli() -> bool:
    try:
        result = subprocess.run(
            [AZURE_CLI_PATH, "version"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=5,
            check=False,
        )
        return result.returncode == 0
    except OSError:
        return False


AZURE_CLI_AVAILABLE = check_azure_cli()
DOCKER_AVAILABLE = False
K8S_AVAILABLE = False

if IS_PRODUCTION and not DATABASE_URL:
    raise RuntimeError("DATABASE_URL must be configured in Azure Key Vault when APP_ENV=production.")
if IS_PRODUCTION and not JWT_SECRET:
    raise RuntimeError("JWT_SECRET must be configured in Azure Key Vault when APP_ENV=production.")
if IS_PRODUCTION and not FRONTEND_URL:
    raise RuntimeError("FRONTEND_URL must be configured in Azure Key Vault when APP_ENV=production.")
if IS_PRODUCTION and FRONTEND_URL.lower().startswith("http://"):
    raise RuntimeError("FRONTEND_URL must use HTTPS when APP_ENV=production.")
if IS_PRODUCTION and not ALLOWED_HOSTS:
    raise RuntimeError("ALLOWED_HOSTS must be configured in Azure Key Vault when APP_ENV=production.")
if IS_PRODUCTION and not DB_SSL_ENABLED:
    raise RuntimeError("DB_SSL_ENABLED must remain enabled when APP_ENV=production.")
if IS_PRODUCTION and not DB_SSL_VERIFY:
    raise RuntimeError("DB_SSL_VERIFY must remain enabled when APP_ENV=production.")
if IS_PRODUCTION and not (SMTP_HOST and SMTP_USERNAME and SMTP_PASSWORD and SMTP_FROM_EMAIL):
    raise RuntimeError("SMTP settings must be configured in Azure Key Vault when APP_ENV=production.")
if IS_PRODUCTION and PHONE_VERIFICATION_REQUIRED and not (
    TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_FROM_NUMBER
):
    raise RuntimeError("Twilio settings must be configured in Azure Key Vault when phone verification is required.")
if not JWT_SECRET:
    JWT_SECRET = secrets.token_urlsafe(48)
    print("WARNING: JWT_SECRET is not configured; generated an ephemeral development secret.")

print("ZeroOps Backend Config:")
print(f"  Azure Key Vault Configured: {bool(AZURE_KEYVAULT_URL)}")
print(f"  Azure Deployment Worker Ready: {AZURE_CLI_AVAILABLE}")
print(f"  Environment: {APP_ENV}")
print(f"  Database Configured: {bool(DATABASE_URL)}")
