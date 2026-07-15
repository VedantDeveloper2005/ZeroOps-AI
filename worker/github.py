import os
import shutil
import subprocess
import urllib.request
import zipfile
import io

def clone_repository(full_name: str, branch: str = "main", token: str = None, work_dir: str = "/tmp") -> str:
    """Clones a GitHub repository to a temporary workspace and returns its path."""
    folder_name = f"{full_name.replace('/', '_')}_{branch}"
    repo_path = os.path.join(work_dir, folder_name)

    # Clean existing directory if present
    if os.path.exists(repo_path):
        try:
            shutil.rmtree(repo_path)
        except Exception as e:
            print(f"Failed to clean directory {repo_path}: {e}")

    # Build clone URL
    if token:
        clone_url = f"https://{token}@github.com/{full_name}.git"
    else:
        clone_url = f"https://github.com/{full_name}.git"

    # Try Git clone
    git_available = shutil.which("git") is not None
    if git_available:
        try:
            # Clone with single branch, depth 1
            cmd = ["git", "clone", "--branch", branch, "--depth", "1", clone_url, repo_path]
            res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=30)
            if res.returncode == 0:
                return repo_path
        except Exception as e:
            print(f"git clone failed: {e}")

    # Fallback to ZIP download
    print(f"Downloading ZIP fallback for {full_name} ({branch})...")
    try:
        url = f"https://api.github.com/repos/{full_name}/zipball/{branch}"
        req = urllib.request.Request(url)
        req.add_header("User-Agent", "ZeroOps-AI-Worker")
        if token:
            req.add_header("Authorization", f"token {token}")
            
        with urllib.request.urlopen(req, timeout=60) as response:
            zip_content = response.read()
        
        # Extract zip
        with zipfile.ZipFile(io.BytesIO(zip_content)) as zip_ref:
            temp_extract_dir = repo_path + "_temp"
            if os.path.exists(temp_extract_dir):
                shutil.rmtree(temp_extract_dir)
            os.makedirs(temp_extract_dir, exist_ok=True)
            zip_ref.extractall(temp_extract_dir)
            
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
            
            # Cleanup temp extract dir
            shutil.rmtree(temp_extract_dir)
            return repo_path
    except Exception as e:
        raise RuntimeError(f"Failed to fetch repository zip fallback: {e}")
