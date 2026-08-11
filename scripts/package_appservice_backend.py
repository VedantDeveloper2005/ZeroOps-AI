"""Build the deterministic Azure App Service backend deployment ZIP.

The App Service artifact must preserve ``backend`` as a Python package.  A
flat copy of ``backend/`` makes ``main.py`` importable but breaks every module
that correctly imports ``backend.services`` or ``backend.contracts``.  Runtime
AI instructions also live outside the package and must be included explicitly.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import stat
import subprocess
import zipfile
from pathlib import Path, PurePosixPath
from typing import Iterable


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = REPOSITORY_ROOT / "backend"
DEFAULT_OUTPUT = REPOSITORY_ROOT / "dist" / "zeroops-backend-appservice.zip"
FIXED_TIMESTAMP = (1980, 1, 1, 0, 0, 0)

RUNTIME_PROMPTS = (
    Path("repository-analysis/instructions.md"),
    Path("terraform-generation/instructions.md"),
)

EXCLUDED_DIRECTORY_NAMES = {
    "__pycache__",
    ".pytest_cache",
    "tests",
    "workspace",
}
EXCLUDED_FILE_NAMES = {
    "requirements.txt",
    "startup.sh",
}


def _backend_entries() -> Iterable[tuple[PurePosixPath, Path]]:
    tracked = subprocess.run(
        [
            "git",
            "-C",
            str(REPOSITORY_ROOT),
            "ls-files",
            "--cached",
            "--others",
            "--exclude-standard",
            "-z",
            "--",
            "backend",
        ],
        check=True,
        capture_output=True,
    ).stdout.split(b"\0")
    for encoded_path in tracked:
        if not encoded_path:
            continue
        repository_relative = Path(os.fsdecode(encoded_path))
        source = REPOSITORY_ROOT / repository_relative
        relative = source.relative_to(BACKEND_ROOT)
        if any(part in EXCLUDED_DIRECTORY_NAMES for part in relative.parts):
            continue
        if source.name in EXCLUDED_FILE_NAMES or source.name.startswith(".env"):
            continue
        if source.suffix in {".pyc", ".pyo"}:
            continue
        if not source.is_file():
            raise FileNotFoundError(f"Tracked deployment source is missing: {relative}")
        if source.is_symlink():
            raise ValueError(f"Deployment source cannot contain symlinks: {relative}")
        yield PurePosixPath("backend", *relative.parts), source


def _runtime_entries() -> list[tuple[PurePosixPath, Path]]:
    entries = [
        (PurePosixPath("startup.sh"), REPOSITORY_ROOT / "startup.sh"),
        (PurePosixPath("requirements.txt"), BACKEND_ROOT / "requirements.txt"),
        *_backend_entries(),
    ]
    entries.extend(
        (
            PurePosixPath("ai-specs", *relative.parts),
            REPOSITORY_ROOT / "ai-specs" / relative,
        )
        for relative in RUNTIME_PROMPTS
    )
    return sorted(entries, key=lambda item: item[0].as_posix())


def _zip_info(name: PurePosixPath) -> zipfile.ZipInfo:
    value = zipfile.ZipInfo(name.as_posix(), FIXED_TIMESTAMP)
    value.create_system = 3
    mode = 0o755 if name.as_posix() == "startup.sh" else 0o644
    value.external_attr = (stat.S_IFREG | mode) << 16
    value.compress_type = zipfile.ZIP_DEFLATED
    return value


def build(output: Path = DEFAULT_OUTPUT) -> tuple[Path, str]:
    output = output.resolve()
    if output.suffix.lower() != ".zip":
        raise ValueError("App Service package output must be a .zip file")

    entries = _runtime_entries()
    names = [name.as_posix() for name, _ in entries]
    if len(names) != len(set(names)):
        raise ValueError("App Service package contains duplicate archive paths")
    for name, source in entries:
        if not source.is_file():
            raise FileNotFoundError(f"Deployment source is missing: {name}")
        if source.is_symlink():
            raise ValueError(f"Deployment source cannot be a symlink: {name}")

    required = {
        "startup.sh",
        "requirements.txt",
        "backend/__init__.py",
        "backend/main.py",
        "backend/services/model_gateway.py",
        "ai-specs/repository-analysis/instructions.md",
        "ai-specs/terraform-generation/instructions.md",
    }
    missing = required.difference(names)
    if missing:
        raise FileNotFoundError(
            "App Service package is missing required inputs: " + ", ".join(sorted(missing))
        )

    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.{os.getpid()}.tmp")
    try:
        with zipfile.ZipFile(
            temporary,
            mode="w",
            compression=zipfile.ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            for name, source in entries:
                archive.writestr(_zip_info(name), source.read_bytes())
        os.replace(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)

    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    return output, digest


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Destination ZIP (default: dist/zeroops-backend-appservice.zip)",
    )
    arguments = parser.parse_args()
    output, digest = build(arguments.output)
    print(f"{output} sha256={digest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
