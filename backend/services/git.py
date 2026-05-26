import os
import shutil
import subprocess
<<<<<<< HEAD
try:
    from backend.config import WORKSPACE_DIR
except ImportError:
    from config import WORKSPACE_DIR
=======
from backend.config import WORKSPACE_DIR
>>>>>>> 7a8a49ab91a776be547d07446a274f5d8f0822b2

def get_repo_path(full_name: str) -> str:
    """Get the local workspace path for a repository full name (e.g. owner/repo)"""
    folder_name = full_name.replace("/", "_")
    return os.path.join(WORKSPACE_DIR, folder_name)

def clone_repo(full_name: str, token: str = None) -> str:
    """Clones a GitHub repository to the local workspace and returns its path."""
    repo_path = get_repo_path(full_name)
    
    # Clean existing directory if present
    if os.path.exists(repo_path):
        try:
            shutil.rmtree(repo_path)
        except Exception as e:
            print(f"Failed to clean directory {repo_path}: {e}")

    # Build authenticated URL if token is present, else standard public URL
    if token:
        clone_url = f"https://{token}@github.com/{full_name}.git"
    else:
        clone_url = f"https://github.com/{full_name}.git"

    print(f"Cloning {full_name} to {repo_path}...")
    try:
        res = subprocess.run(
            ["git", "clone", "--depth", "1", clone_url, repo_path],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30
        )
        if res.returncode == 0:
            print(f"Cloned successfully to {repo_path}")
            return repo_path
    except Exception as e:
        print(f"Git command failed: {e}")

    # Fallback/Mock mode: Create a dummy repository structure to simulate cloning
    print(f"Using high-fidelity mockup workspace for {full_name}")
    os.makedirs(repo_path, exist_ok=True)
    
    # Create package.json to mimic a Next.js app for default detections
    package_json_content = """{
<<<<<<< HEAD
    "name": "zeroops-demo-app",
  "version": "0.1.0",
  "private": true,
  "dependencies": {
    "next": "^16.2.6",
    "react": "^19.2.4",
    "react-dom": "^19.2.4",
    "framer-motion": "^12.40.0",
    "tailwindcss": "^4.0.0"
  },
  "devDependencies": {
    "typescript": "^5.7.0"
=======
  "name": "nextjs-demo",
  "version": "0.1.0",
  "private": true,
  "dependencies": {
    "next": "^15.1.0",
    "react": "^19.0.0",
    "react-dom": "^19.0.0",
    "framer-motion": "^11.0.0",
    "tailwindcss": "^4.0.0"
>>>>>>> 7a8a49ab91a776be547d07446a274f5d8f0822b2
  }
}"""
    with open(os.path.join(repo_path, "package.json"), "w") as f:
        f.write(package_json_content)

    return repo_path

def get_branches(full_name: str, token: str = None) -> list[str]:
    """Fetch remote branches for a repository."""
    if token:
        url = f"https://{token}@github.com/{full_name}.git"
    else:
        url = f"https://github.com/{full_name}.git"

    try:
        res = subprocess.run(
            ["git", "ls-remote", "--heads", url],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )
        if res.returncode == 0:
            branches = []
            for line in res.stdout.strip().split("\n"):
                if line:
                    # Line format: hash refs/heads/branch_name
                    ref = line.split("\t")[1]
                    branch_name = ref.replace("refs/heads/", "")
                    branches.append(branch_name)
            return branches if branches else ["main"]
    except Exception:
        pass

    # Mock list
    return ["main", "develop", "feature/auth"]
