"""Regression tests for the Azure App Service deployment artifact."""

from __future__ import annotations

import os
import subprocess
import sys
import textwrap
import zipfile
from pathlib import Path, PurePosixPath


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
PACKAGER = REPOSITORY_ROOT / "scripts" / "package_appservice_backend.py"
WORKFLOW = REPOSITORY_ROOT / ".github" / "workflows" / "main_zeroops-backend.yml"


def _build_package(output: Path) -> bytes:
    result = subprocess.run(
        [sys.executable, str(PACKAGER), "--output", str(output)],
        cwd=REPOSITORY_ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    assert "sha256=" in result.stdout
    return output.read_bytes()


def test_package_is_deterministic_and_has_canonical_layout(tmp_path: Path) -> None:
    first = tmp_path / "first.zip"
    second = tmp_path / "second.zip"

    assert _build_package(first) == _build_package(second)

    with zipfile.ZipFile(first) as archive:
        names = set(archive.namelist())
        required = {
            "startup.sh",
            "requirements.txt",
            "backend/__init__.py",
            "backend/main.py",
            "backend/services/model_gateway.py",
            "backend/services/providers/groq.py",
            "backend/services/terraform_ai.py",
            "ai-specs/repository-analysis/instructions.md",
            "ai-specs/terraform-generation/instructions.md",
        }
        assert required <= names
        assert "main.py" not in names
        assert "services/ai.py" not in names
        assert "backend/requirements.txt" not in names
        assert "backend/startup.sh" not in names

        excluded_parts = {"tests", "workspace", "__pycache__", ".pytest_cache"}
        assert not any(
            excluded_parts.intersection(PurePosixPath(name).parts) for name in names
        )
        assert not any(Path(name).name.startswith(".env") for name in names)
        assert not any(name.endswith((".pyc", ".pyo")) for name in names)


def test_extracted_package_imports_and_loads_runtime_prompts(tmp_path: Path) -> None:
    package = tmp_path / "backend.zip"
    extracted = tmp_path / "site"
    _build_package(package)

    with zipfile.ZipFile(package) as archive:
        archive.extractall(extracted)

    probe = textwrap.dedent(
        """
        from pathlib import Path

        import backend
        import backend.main
        import backend.services.model_gateway as model_gateway
        import backend.services.providers
        import backend.services.providers.groq
        import backend.services.terraform_ai as terraform_ai

        artifact_root = Path.cwd().resolve()
        assert artifact_root in Path(backend.__file__).resolve().parents
        assert backend.main.app is not None
        assert model_gateway.load_repository_instructions().strip()
        assert terraform_ai.load_terraform_instructions().strip()
        """
    )
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    environment.update(
        {
            "APP_ENV": "test",
            "AZURE_KEYVAULT_URL": "",
        }
    )
    subprocess.run(
        [sys.executable, "-c", probe],
        cwd=extracted,
        env=environment,
        check=True,
        capture_output=True,
        text=True,
    )

    if os.name != "nt":
        subprocess.run(
            ["bash", "-n", str(extracted / "startup.sh")],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [sys.executable, "-m", "gunicorn", "--check-config", "backend.main:app"],
            cwd=extracted,
            env=environment,
            check=True,
            capture_output=True,
            text=True,
        )


def test_workflow_deploys_the_canonical_zip() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")
    root_startup = (REPOSITORY_ROOT / "startup.sh").read_text(encoding="utf-8")
    backend_startup = (REPOSITORY_ROOT / "backend" / "startup.sh").read_text(
        encoding="utf-8"
    )

    assert "python scripts/package_appservice_backend.py" in workflow
    assert "path: dist/zeroops-backend-appservice.zip" in workflow
    assert "package: dist/zeroops-backend-appservice.zip" in workflow
    assert "\n          path: backend/\n" not in workflow
    assert "python -m gunicorn backend.main:app" in root_startup
    assert "python -m gunicorn backend.main:app" in backend_startup


def test_workflow_serializes_onedeploy_runs() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "group: zeroops-backend-${{ github.ref }}" in workflow
    assert "cancel-in-progress: false" in workflow
