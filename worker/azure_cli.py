"""Small Azure CLI readiness checks for the legacy local worker entrypoint.

The module intentionally is not named ``azure`` because that shadows the
Microsoft Azure SDK namespace when Python starts inside the worker directory.
The production VMSS executor authenticates with managed identity and does not
depend on an interactive Azure CLI session.
"""

from __future__ import annotations

import shutil
import subprocess


def is_azure_cli_available() -> bool:
    """Return whether an Azure CLI executable is available."""

    return shutil.which("az") is not None or shutil.which("az.cmd") is not None


def check_azure_login() -> bool:
    """Return whether the local CLI currently has a usable account context."""

    try:
        result = subprocess.run(
            ["az", "account", "show"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return result.returncode == 0
