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

ALLOW_CREDENTIALS = True

# OpenAI API config
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

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

# Azure deployment configuration. User-specific Azure targets are stored in DB.
AZURE_DEFAULT_REGION = os.getenv("AZURE_DEFAULT_REGION", "eastus")
ZEROOPS_PUBLIC_BASE_DOMAIN = os.getenv("ZEROOPS_PUBLIC_BASE_DOMAIN", "").strip().strip(".")

# Azure BYOS (Bring Your Own Subscription) configuration
# ZeroOps Key Vault URL – used to store customer SP secrets via Managed Identity.
# Leave empty to fall back to local mock secret storage (dev only).
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

# Workspace folder for temporary checkouts
WORKSPACE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "workspace"))
os.makedirs(WORKSPACE_DIR, exist_ok=True)

# Autodetect runtime environments
def check_docker():
    try:
        # Run docker ps with short timeout to verify daemon responsiveness
        res = subprocess.run(["docker", "ps"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        return res.returncode == 0
    except Exception:
        return False

def check_kubernetes():
    try:
        # Run kubectl config current-context to verify context existence
        res = subprocess.run(["kubectl", "config", "current-context"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
        return res.returncode == 0
    except Exception:
        return False

DOCKER_AVAILABLE = check_docker()
K8S_AVAILABLE = check_kubernetes()

# Database & Authentication configurations
DATABASE_URL = os.getenv("DATABASE_URL", "")
JWT_SECRET = os.getenv("JWT_SECRET", "")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080")) # 7 days

if IS_PRODUCTION and not DATABASE_URL:
    raise RuntimeError("DATABASE_URL must be configured when APP_ENV=production.")

if IS_PRODUCTION and not JWT_SECRET:
    raise RuntimeError("JWT_SECRET must be configured when APP_ENV=production.")

if IS_PRODUCTION and not FRONTEND_URL:
    raise RuntimeError("FRONTEND_URL or FRONTEND_ORIGIN must be configured when APP_ENV=production.")

if IS_PRODUCTION and FRONTEND_URL.lower().startswith("http://"):
    raise RuntimeError("FRONTEND_URL must use HTTPS when APP_ENV=production.")

if not JWT_SECRET:
    JWT_SECRET = secrets.token_urlsafe(48)
    print("  WARNING: JWT_SECRET is not set. Generated an ephemeral local-development secret.")

print(f"ZeroOps Backend Config:")
print(f"  Docker Host Responsive: {DOCKER_AVAILABLE}")
print(f"  Kubernetes Context Active: {K8S_AVAILABLE}")
print(f"  OpenAI API Key Configured: {bool(OPENAI_API_KEY)}")
print(f"  Environment: {APP_ENV}")
print(f"  CORS Origins: {', '.join(CORS_ORIGINS)}")
print(f"  Workspace Directory: {WORKSPACE_DIR}")
print(f"  Database Configured: {bool(DATABASE_URL)}")
print(f"  JWT Secret Configured: {bool(JWT_SECRET)}")
if not DATABASE_URL:
    print("  WARNING: DATABASE_URL is not set. Database storage features will be unavailable.")
