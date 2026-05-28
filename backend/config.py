import os
import subprocess
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

# App settings
PORT = int(os.getenv("PORT", 8000))
HOST = os.getenv("HOST", "0.0.0.0")
APP_ENV = os.getenv("APP_ENV", os.getenv("ENVIRONMENT", "development"))
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "")
ZEROOPS_BACKEND_URL = os.getenv("ZEROOPS_BACKEND_URL", "")

def parse_csv_env(name: str, default: str = "") -> list[str]:
    raw = os.getenv(name, default)
    return [item.strip() for item in raw.split(",") if item.strip()]

CORS_ORIGINS = parse_csv_env("CORS_ORIGINS", FRONTEND_ORIGIN or "*")
ALLOW_CREDENTIALS = "*" not in CORS_ORIGINS

# OpenAI API config
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# GitHub API config
# Users can supply a fallback GitHub Personal Access Token (PAT) for listing real private/public repos
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

# GitHub OAuth App credentials (create at https://github.com/settings/developers)
GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID", "")
GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET", "")
GITHUB_OAUTH_SCOPES = os.getenv("GITHUB_OAUTH_SCOPES", "repo,read:user,user:email")

# Frontend URL for OAuth redirect (after callback, redirect user here)
FRONTEND_URL = os.getenv("FRONTEND_URL", os.getenv("FRONTEND_ORIGIN", "http://localhost:3000"))

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
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://zeroopsadmin:Ved%402005%23@zeroops-db-vedant.postgres.database.azure.com:5432/zeroops")
JWT_SECRET = os.getenv("JWT_SECRET", "zeroops_super_secure_jwt_secret_2026")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "10080")) # 7 days

print(f"ZeroOps Backend Config:")
print(f"  Docker Host Responsive: {DOCKER_AVAILABLE}")
print(f"  Kubernetes Context Active: {K8S_AVAILABLE}")
print(f"  OpenAI API Key Configured: {bool(OPENAI_API_KEY)}")
print(f"  Environment: {APP_ENV}")
print(f"  CORS Origins: {', '.join(CORS_ORIGINS)}")
print(f"  Workspace Directory: {WORKSPACE_DIR}")
print(f"  Database Configured: {bool(DATABASE_URL)}")
print(f"  JWT Secret Configured: {bool(JWT_SECRET)}")

