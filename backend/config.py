import os
import subprocess
from dotenv import load_dotenv

# Load .env file if present
load_dotenv()

# App settings
PORT = int(os.getenv("PORT", 8000))
HOST = os.getenv("HOST", "0.0.0.0")

# OpenAI API config
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# GitHub API config
# Users can supply a fallback GitHub Personal Access Token (PAT) for listing real private/public repos
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")

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

print(f"ZeroOps Backend Config:")
print(f"  Docker Host Responsive: {DOCKER_AVAILABLE}")
print(f"  Kubernetes Context Active: {K8S_AVAILABLE}")
print(f"  OpenAI API Key Configured: {bool(OPENAI_API_KEY)}")
print(f"  Workspace Directory: {WORKSPACE_DIR}")
