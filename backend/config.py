import os
import secrets
import subprocess
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

# App settings
PORT = int(os.getenv("PORT", 8000))
HOST = os.getenv("HOST", "0.0.0.0")
APP_ENV = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development")).lower()
IS_PRODUCTION = APP_ENV == "production"
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "").rstrip("/")
FRONTEND_URL = os.getenv("FRONTEND_URL", FRONTEND_ORIGIN).rstrip("/")
if not FRONTEND_URL and not IS_PRODUCTION:
    FRONTEND_URL = "http://localhost:3000"
ZEROOPS_BACKEND_URL = os.getenv("ZEROOPS_BACKEND_URL", "")

DEFAULT_ALLOWED_ORIGINS = [FRONTEND_URL] if FRONTEND_URL else []

if not IS_PRODUCTION:
    DEFAULT_ALLOWED_ORIGINS.extend([
        "http://localhost:3000",
        "http://127.0.0.1:3000"
    ])

def parse_csv_env(name: str, default_origins: list[str]) -> list[str]:
    raw = os.getenv(name, "")
    if not raw:
        return default_origins.copy()
    parsed = [item.strip() for item in raw.split(",") if item.strip()]
    if "*" in parsed:
        parsed = [p for p in parsed if p != "*"]
        for origin in default_origins:
            if origin not in parsed:
                parsed.append(origin)
    return parsed

CORS_ORIGINS = parse_csv_env("CORS_ORIGINS", DEFAULT_ALLOWED_ORIGINS)

# Inject FRONTEND_ORIGIN and FRONTEND_URL if they are not already in CORS_ORIGINS
for url in [FRONTEND_ORIGIN, FRONTEND_URL]:
    if url:
        clean_url = url.rstrip("/")
        if clean_url not in CORS_ORIGINS:
            CORS_ORIGINS.append(clean_url)

# Remove duplicates while preserving order
CORS_ORIGINS = list(dict.fromkeys(CORS_ORIGINS))
ALLOWED_HOSTS = parse_csv_env("ALLOWED_HOSTS", ["*"] if not IS_PRODUCTION else [])

ALLOW_CREDENTIALS = True

# OpenAI API config
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
# Repository analysis is a bounded review task.  Keep the model setting on the
# server so customers never need to know, select, or receive a model identifier.
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-5.4-mini")
AI_MODEL_TIMEOUT_SECONDS = int(os.getenv("AI_MODEL_TIMEOUT_SECONDS", "30"))

# GitHub Models API config
GITHUB_MODELS_API_KEY = os.getenv("GITHUB_MODELS_API_KEY", "")
GITHUB_MODELS_ENDPOINT = os.getenv("GITHUB_MODELS_ENDPOINT", "https://models.inference.ai.azure.com")
GITHUB_MODELS_MODEL = os.getenv("GITHUB_MODELS_MODEL", "gpt-4o")

# NVIDIA API config
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_ENDPOINT = os.getenv("NVIDIA_ENDPOINT", "https://integrate.api.nvidia.com/v1")
NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "nvidia/llama-3.1-nemotron-70b-instruct")

# GitHub API config
# Users can supply a fallback GitHub Personal Access Token (PAT) for listing real private/public repos
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# GitHub OAuth App credentials (create at https://github.com/settings/developers)
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
GITHUB_OAUTH_SCOPES = os.getenv("GITHUB_OAUTH_SCOPES", "repo,read:user,user:email")

# Google OAuth App credentials
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
GOOGLE_CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET", "")
GOOGLE_OAUTH_SCOPES = os.getenv("GOOGLE_OAUTH_SCOPES", "openid email profile")

# MFA configuration. MFA_ENCRYPTION_KEY should be a dedicated Fernet key in
# production. When it is intentionally omitted, the application derives a
# compatibility key from JWT_SECRET so existing environments can adopt MFA
# without invalidating their current configuration.
MFA_ENCRYPTION_KEY = os.getenv("MFA_ENCRYPTION_KEY", "")
MFA_ISSUER = os.getenv("MFA_ISSUER", "ZeroOps AI")
MFA_CHALLENGE_EXPIRE_MINUTES = int(os.getenv("MFA_CHALLENGE_EXPIRE_MINUTES", "5"))
MFA_REAUTH_WINDOW_MINUTES = int(os.getenv("MFA_REAUTH_WINDOW_MINUTES", "10"))

# SMTP email configuration
SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", "")
SMTP_USE_TLS = os.getenv("SMTP_USE_TLS", "true").lower() == "true"

# Email verification settings
EMAIL_VERIFICATION_EXPIRE_HOURS = int(os.getenv("EMAIL_VERIFICATION_EXPIRE_HOURS", "24"))
EMAIL_OTP_EXPIRE_MINUTES = int(os.getenv("EMAIL_OTP_EXPIRE_MINUTES", "10"))
EMAIL_OTP_LENGTH = int(os.getenv("EMAIL_OTP_LENGTH", "6"))

# Azure deployment configuration. User-specific Azure targets are stored in DB.
AZURE_DEFAULT_REGION = os.getenv("AZURE_DEFAULT_REGION", "eastus")
ZEROOPS_PUBLIC_BASE_DOMAIN = os.getenv("ZEROOPS_PUBLIC_BASE_DOMAIN", "").strip().strip(".")

# Azure BYOS (Bring Your Own Subscription) configuration. Customer deployment
# credentials and application secrets are held only in this Key Vault.
AZURE_KEYVAULT_URL = os.getenv("AZURE_KEYVAULT_URL", "")

# Risk classifier thresholds
RISK_COST_THRESHOLD_CENTS = int(os.getenv("RISK_COST_THRESHOLD_CENTS", "5000"))  # $50
# UTC time range during which production changes are allowed without high-risk escalation.
# Format: "HH:MM-HH:MM" e.g. "02:00-06:00". Empty = all production ops require approval.
MAINTENANCE_WINDOW_UTC = os.getenv("MAINTENANCE_WINDOW_UTC", "")

# Paid AI operation controls
PAYMENT_PROVIDER = os.getenv("PAYMENT_PROVIDER", "manual")
AI_PAID_OPERATION_PRICE_CENTS = int(os.getenv("AI_PAID_OPERATION_PRICE_CENTS", "499"))
AI_FREE_DAILY_LIMIT = int(os.getenv("AI_FREE_DAILY_LIMIT", "5"))
STRIPE_SECRET_KEY = os.getenv("STRIPE_SECRET_KEY", "")
STRIPE_WEBHOOK_SECRET = os.getenv("STRIPE_WEBHOOK_SECRET", "")

# Direct upload controls
MAX_CODE_UPLOAD_MB = int(os.getenv("MAX_CODE_UPLOAD_MB", "50"))
MAX_UPLOAD_ARCHIVE_FILES = int(os.getenv("MAX_UPLOAD_ARCHIVE_FILES", "10000"))
MAX_UPLOAD_UNCOMPRESSED_MB = int(os.getenv("MAX_UPLOAD_UNCOMPRESSED_MB", "250"))
MAX_UPLOAD_COMPRESSION_RATIO = int(os.getenv("MAX_UPLOAD_COMPRESSION_RATIO", "100"))
MAX_RATE_LIMIT_KEYS = int(os.getenv("MAX_RATE_LIMIT_KEYS", "10000"))
DB_SSL_VERIFY = os.getenv("DB_SSL_VERIFY", "true").lower() == "true"

# Workspace folder for temporary checkouts
WORKSPACE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "workspace"))
os.makedirs(WORKSPACE_DIR, exist_ok=True)

# Deployment workers build remotely in Azure Container Registry, so the control
# plane intentionally does not depend on Docker or a cluster context.
AZURE_CLI_PATH = os.getenv("AZURE_CLI_PATH", "az")

def check_azure_cli():
    try:
        res = subprocess.run([AZURE_CLI_PATH, "version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
        return res.returncode == 0
    except Exception:
        return False

AZURE_CLI_AVAILABLE = check_azure_cli()
# Compatibility flags for retired internal modules. They are intentionally
# always false: no production launch path can fall back to local Docker or a
# cluster context.
DOCKER_AVAILABLE = False
K8S_AVAILABLE = False

# Database & Authentication configurations
DATABASE_URL = os.getenv("DATABASE_URL", "")
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "15"))
REFRESH_TOKEN_EXPIRE_DAYS = int(os.getenv("REFRESH_TOKEN_EXPIRE_DAYS", "7"))

if IS_PRODUCTION and not DATABASE_URL:
    raise RuntimeError("DATABASE_URL must be configured when APP_ENV=production.")

if IS_PRODUCTION and not JWT_SECRET:
    raise RuntimeError("JWT_SECRET must be configured when APP_ENV=production.")

if IS_PRODUCTION and not FRONTEND_URL:
    raise RuntimeError("FRONTEND_URL or FRONTEND_ORIGIN must be configured when APP_ENV=production.")

if IS_PRODUCTION and FRONTEND_URL.lower().startswith("http://"):
    raise RuntimeError("FRONTEND_URL must use HTTPS when APP_ENV=production.")

if IS_PRODUCTION and not AZURE_KEYVAULT_URL:
    raise RuntimeError("AZURE_KEYVAULT_URL must be configured when APP_ENV=production.")

if IS_PRODUCTION and not ALLOWED_HOSTS:
    raise RuntimeError("ALLOWED_HOSTS must list the public API hostname when APP_ENV=production.")

if IS_PRODUCTION and not DB_SSL_VERIFY:
    raise RuntimeError("DB_SSL_VERIFY must remain enabled when APP_ENV=production.")

if not JWT_SECRET:
    JWT_SECRET = secrets.token_urlsafe(48)
    print("  WARNING: JWT_SECRET is not set. Generated an ephemeral local-development secret.")

print(f"ZeroOps Backend Config:")
print(f"  Azure Deployment Worker Ready: {AZURE_CLI_AVAILABLE}")
print(f"  OpenAI API Key Configured: {bool(OPENAI_API_KEY)}")
print(f"  Environment: {APP_ENV}")
print(f"  CORS Origins: {', '.join(CORS_ORIGINS)}")
print(f"  Workspace Directory: {WORKSPACE_DIR}")
print(f"  Database Configured: {bool(DATABASE_URL)}")
print(f"  JWT Secret Configured: {bool(JWT_SECRET)}")
if not DATABASE_URL:
    print("  WARNING: DATABASE_URL is not set. Database storage features will be unavailable.")
