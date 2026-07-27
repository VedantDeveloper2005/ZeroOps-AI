import os
import shutil
import subprocess
try:
    from backend.config import WORKSPACE_DIR
except ImportError:
    from config import WORKSPACE_DIR

import os
import shutil
import subprocess
import base64
import re
import stat
try:
    from backend.config import WORKSPACE_DIR
except ImportError:
    from config import WORKSPACE_DIR

_GITHUB_REPOSITORY_PATTERN = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9])?/[A-Za-z0-9](?:[A-Za-z0-9._-]{0,98}[A-Za-z0-9])?$"
)


def _validated_repository_name(full_name: str) -> str:
    """Accept only an owner/repository identifier, never a URL or local path."""
    if not isinstance(full_name, str) or not _GITHUB_REPOSITORY_PATTERN.fullmatch(full_name):
        raise ValueError("Repository must use the GitHub owner/repository format.")
    return full_name


def _git_environment(token: str | None) -> dict[str, str]:
    """Supply an OAuth token without placing it in the git command line."""
    environment = os.environ.copy()
    environment["GIT_TERMINAL_PROMPT"] = "0"
    if token:
        credentials = base64.b64encode(f"x-access-token:{token}".encode("utf-8")).decode("ascii")
        environment["GIT_CONFIG_COUNT"] = "1"
        environment["GIT_CONFIG_KEY_0"] = "http.extraHeader"
        environment["GIT_CONFIG_VALUE_0"] = f"Authorization: Basic {credentials}"
    return environment


def _safe_extract(zip_file, destination: str) -> None:
    """Reject path traversal and symlinks before extracting a GitHub archive."""
    destination_root = os.path.realpath(destination)
    destination_prefix = destination_root + os.sep
    for member in zip_file.infolist():
        target = os.path.realpath(os.path.join(destination_root, member.filename))
        if target != destination_root and not target.startswith(destination_prefix):
            raise RuntimeError("Repository archive contains an unsafe path.")
        if stat.S_ISLNK(member.external_attr >> 16):
            raise RuntimeError("Repository archive contains an unsupported symbolic link.")
    zip_file.extractall(destination_root)


def get_repo_path(full_name: str) -> str:
    """Get the local workspace path for a repository full name (e.g. owner/repo)"""
    full_name = _validated_repository_name(full_name)
    folder_name = full_name.replace("/", "_")
    return os.path.join(WORKSPACE_DIR, folder_name)

def clone_repo(full_name: str, token: str = None) -> str:
    """Clones a GitHub repository to the local workspace and returns its path.
    Falls back to zipball download if git binary is not present or clone fails.
    """
    import shutil
    import subprocess
    full_name = _validated_repository_name(full_name)
    repo_path = get_repo_path(full_name)
    
    # Clean existing directory if present
    if os.path.exists(repo_path):
        try:
            shutil.rmtree(repo_path)
        except Exception as e:
            print(f"Failed to clean directory {repo_path}: {e}")

    clone_url = f"https://github.com/{full_name}.git"

    print(f"Cloning {full_name} to {repo_path}...")
    
    # Check if git is available
    git_available = shutil.which("git") is not None
    if git_available:
        try:
            res = subprocess.run(
                ["git", "clone", "--depth", "1", clone_url, repo_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=30,
                env=_git_environment(token),
            )
            if res.returncode == 0:
                print(f"Cloned successfully to {repo_path}")
                return repo_path
            print(f"git clone failed with exit code {res.returncode}. Trying zipball fallback.")
        except Exception as e:
            print(f"git clone error: {e}. Trying zipball fallback.")
    else:
        print("git executable not found on PATH. Using zipball fallback.")

    # Fallback to ZIP download
    print(f"Downloading zipball fallback for {full_name}...")
    try:
        import urllib.request
        import zipfile
        import io
        
        # Try default branch first (e.g. main/master)
        for branch in ["main", "master"]:
            try:
                url = f"https://api.github.com/repos/{full_name}/zipball/{branch}"
                req = urllib.request.Request(url)
                req.add_header("User-Agent", "ZeroOps-AI-Deployment")
                if token:
                    req.add_header("Authorization", f"Bearer {token}")
                    
                with urllib.request.urlopen(req, timeout=60) as response:
                    zip_content = response.read()
                
                # Extract zip
                with zipfile.ZipFile(io.BytesIO(zip_content)) as zip_ref:
                    temp_extract_dir = repo_path + "_temp"
                    if os.path.exists(temp_extract_dir):
                        shutil.rmtree(temp_extract_dir)
                    os.makedirs(temp_extract_dir, exist_ok=True)
                    _safe_extract(zip_ref, temp_extract_dir)
                    
                    subdirs = [d for d in os.listdir(temp_extract_dir) if os.path.isdir(os.path.join(temp_extract_dir, d))]
                    if subdirs:
                        src_dir = os.path.join(temp_extract_dir, subdirs[0])
                        os.makedirs(repo_path, exist_ok=True)
                        for item in os.listdir(src_dir):
                            s = os.path.join(src_dir, item)
                            d = os.path.join(repo_path, item)
                            if os.path.isdir(s):
                                shutil.copytree(s, d)
                            else:
                                shutil.copy2(s, d)
                    shutil.rmtree(temp_extract_dir)
                print(f"Successfully extracted zipball to {repo_path}")
                return repo_path
            except Exception as branch_err:
                print(f"Zipball fallback failed for branch {branch}: {branch_err}")
                continue
                
        raise RuntimeError("GitHub zipball download failed on both main and master branches.")
    except Exception as e:
        raise RuntimeError(f"Unable to fetch repository '{full_name}' via clone or zipball: {e}") from e

def get_branches(full_name: str, token: str = None) -> list[str]:
    """Fetch remote branches for a repository."""
    full_name = _validated_repository_name(full_name)
    import shutil
    import subprocess
    
    # Try git first if available
    git_available = shutil.which("git") is not None
    if git_available:
        url = f"https://github.com/{full_name}.git"

        try:
            res = subprocess.run(
                ["git", "ls-remote", "--heads", url],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=10,
                env=_git_environment(token),
            )
            if res.returncode == 0:
                branches = []
                for line in res.stdout.strip().split("\n"):
                    if line:
                        ref = line.split("\t")[1]
                        branch_name = ref.replace("refs/heads/", "")
                        branches.append(branch_name)
                return branches if branches else ["main"]
        except Exception:
            pass

    # Fallback to GitHub API branches endpoint using urllib
    print(f"git ls-remote failed or git missing. Querying branches API for {full_name}...")
    try:
        import urllib.request
        import json
        url = f"https://api.github.com/repos/{full_name}/branches?per_page=100"
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "ZeroOps-AI-Deployment")
        req.add_header("Accept", "application/vnd.github+json")
        if token:
            req.add_header("Authorization", f"Bearer {token}")
            
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode("utf-8"))
            branches = [b.get("name") for b in data if b.get("name")]
            return branches if branches else ["main"]
    except Exception as e:
        print(f"GitHub branches API fallback failed: {e}")
        pass

    return ["main"]
