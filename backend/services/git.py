import os
import shutil
import subprocess
try:
    from backend.config import WORKSPACE_DIR
except ImportError:
    from config import WORKSPACE_DIR

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
        raise RuntimeError(res.stderr.strip() or f"git clone failed with exit code {res.returncode}")
    except Exception as e:
        raise RuntimeError(f"Unable to clone GitHub repository '{full_name}': {e}") from e

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

    return []
