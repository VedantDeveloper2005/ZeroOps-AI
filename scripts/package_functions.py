"""Build deterministic, workload-isolated Azure Functions deployment ZIPs.

The repository keeps shared Function code and model instructions outside each
Function project. Azure Functions expects every dependency at the ZIP root, so
this script assembles the exact runtime layout and records a SHA-256 manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import shutil
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS_ROOT = REPOSITORY_ROOT / "functions"
COMMON_PACKAGE = FUNCTIONS_ROOT / "common" / "zeroops_functions"
CANONICAL_AI_CONTRACT = REPOSITORY_ROOT / "backend" / "contracts" / "ai.py"
FUNCTION_AI_CONTRACT = COMMON_PACKAGE / "ai_contracts.py"
SCHEMA_GENERATOR = REPOSITORY_ROOT / "scripts" / "generate_ai_schemas.py"
FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)


@dataclass(frozen=True)
class FunctionPackage:
    name: str
    prompt: Path | None
    runtime_assets: tuple[str, ...] = ()


PACKAGES = (
    FunctionPackage(
        name="repository_analysis",
        prompt=REPOSITORY_ROOT / "ai-specs" / "repository-analysis" / "instructions.md",
    ),
    FunctionPackage(
        name="terraform_generation",
        prompt=REPOSITORY_ROOT / "ai-specs" / "terraform-generation" / "instructions.md",
        runtime_assets=("terraform.lock.hcl",),
    ),
    FunctionPackage(name="history_projector", prompt=None),
)


def _normalized_source(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n").rstrip()


def _assert_generated_assets_current() -> None:
    if _normalized_source(CANONICAL_AI_CONTRACT) != _normalized_source(
        FUNCTION_AI_CONTRACT
    ):
        raise RuntimeError(
            "Function AI contracts differ from backend/contracts/ai.py. "
            "Synchronize the mirror before packaging."
        )
    specification = importlib.util.spec_from_file_location(
        "zeroops_generate_ai_schemas",
        SCHEMA_GENERATOR,
    )
    if specification is None or specification.loader is None:
        raise RuntimeError("AI schema generator could not be loaded.")
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    stale = module.generate(check=True)
    if stale:
        relative = ", ".join(
            str(path.relative_to(REPOSITORY_ROOT)) for path in stale
        )
        raise RuntimeError(f"Generated AI schemas are stale: {relative}")


def _copy_project(package: FunctionPackage, staging_root: Path) -> Path:
    project_root = FUNCTIONS_ROOT / package.name
    required = ("function_app.py", "handler.py", "host.json", "requirements.txt")
    missing = [name for name in required if not (project_root / name).is_file()]
    if missing:
        raise FileNotFoundError(
            f"{package.name} is missing required files: {', '.join(missing)}"
        )
    if not COMMON_PACKAGE.is_dir():
        raise FileNotFoundError(f"Shared Function package is missing: {COMMON_PACKAGE}")

    destination = staging_root / package.name
    destination.mkdir(parents=True, exist_ok=False)
    for filename in required:
        shutil.copy2(project_root / filename, destination / filename)
    for filename in package.runtime_assets:
        source = project_root / filename
        if not source.is_file():
            raise FileNotFoundError(
                f"{package.name} runtime asset is missing: {filename}"
            )
        shutil.copy2(source, destination / filename)
    shutil.copytree(
        COMMON_PACKAGE,
        destination / "zeroops_functions",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )

    if package.prompt is not None:
        if not package.prompt.is_file():
            raise FileNotFoundError(f"Function instructions are missing: {package.prompt}")
        prompt_directory = destination / "prompts"
        prompt_directory.mkdir()
        shutil.copy2(package.prompt, prompt_directory / "instructions.md")

    forbidden = tuple(destination.rglob("__pycache__")) + tuple(
        destination.rglob("*.pyc")
    )
    if forbidden:
        raise RuntimeError(
            f"{package.name} package contains generated Python cache files."
        )
    return destination


def _write_deterministic_zip(source: Path, destination: Path) -> str:
    with zipfile.ZipFile(
        destination,
        mode="w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in sorted(item for item in source.rglob("*") if item.is_file()):
            relative = path.relative_to(source).as_posix()
            info = zipfile.ZipInfo(relative, date_time=FIXED_ZIP_TIMESTAMP)
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            archive.writestr(info, path.read_bytes(), compresslevel=9)

    return hashlib.sha256(destination.read_bytes()).hexdigest()


def build(output_root: Path) -> dict[str, dict[str, str | int]]:
    _assert_generated_assets_current()
    output_root = output_root.resolve()
    staging_root = output_root / "staging"
    packages_root = output_root / "packages"
    if output_root.exists():
        shutil.rmtree(output_root)
    staging_root.mkdir(parents=True)
    packages_root.mkdir(parents=True)

    manifest: dict[str, dict[str, str | int]] = {}
    for package in PACKAGES:
        staging = _copy_project(package, staging_root)
        archive = packages_root / f"{package.name}.zip"
        digest = _write_deterministic_zip(staging, archive)
        manifest[package.name] = {
            "archive": archive.relative_to(output_root).as_posix(),
            "sha256": digest,
            "size_bytes": archive.stat().st_size,
        }

    manifest_path = output_root / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "schema_version": "zeroops-function-packages.v1",
                "packages": manifest,
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=REPOSITORY_ROOT / "dist" / "functions",
    )
    arguments = parser.parse_args()
    manifest = build(arguments.output)
    for name, details in manifest.items():
        print(f"{name}: {details['sha256']} ({details['size_bytes']} bytes)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
