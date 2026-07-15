import shutil
import subprocess

def is_azure_cli_available() -> bool:
    """Check if Azure CLI is installed on the worker environment."""
    return (shutil.which("az") is not None) or (shutil.which("az.cmd") is not None)

def check_azure_login() -> bool:
    """Verify if the worker has an active authenticated session with Azure."""
    try:
        res = subprocess.run(["az", "account", "show"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=10)
        return res.returncode == 0
    except Exception:
        return False
