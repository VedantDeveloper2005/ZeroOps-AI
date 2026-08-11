"""Bounded, secret-aware repository snapshots for change detection.

The deployment worker needs content hashes, not an unbounded copy of a source
tree.  This module walks a checked-out repository without following links,
omits generated/vendor directories, and replaces large files with a framed
content digest.  Environment files are represented by their path only so a
persisted repository fingerprint cannot become an offline secret oracle.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import os
from pathlib import Path
import re
from typing import Iterable


MAX_FILES = 25_000
MAX_TOTAL_BYTES = 128 * 1024 * 1024
MAX_INLINE_FILE_BYTES = 2 * 1024 * 1024

_IGNORED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".next",
        ".pytest_cache",
        ".ruff_cache",
        ".svn",
        "__pycache__",
        "build",
        "coverage",
        "dist",
        "node_modules",
        "target",
        "vendor",
    }
)
_ENV_NAME = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class RepositorySnapshotError(RuntimeError):
    """Raised when source evidence cannot be bounded or read safely."""


@dataclass(frozen=True)
class RepositorySnapshot:
    files: dict[str, bytes]
    paths: tuple[str, ...]
    environment_variable_names: tuple[str, ...]
    file_count: int
    represented_bytes: int


def _is_environment_file(path: Path) -> bool:
    name = path.name.lower()
    return name == ".env" or name.startswith(".env.")


def _extract_environment_names(content: bytes) -> Iterable[str]:
    # Values are never returned.  Bound parsing to the same per-file limit as
    # inline fingerprint data and ignore malformed/binary lines.
    text = content[:MAX_INLINE_FILE_BYTES].decode("utf-8", errors="ignore")
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        name = line.split("=", 1)[0].strip()
        if _ENV_NAME.fullmatch(name):
            yield name


def _large_file_marker(path: Path) -> bytes:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return b"zeroops-large-file-sha256:" + digest.hexdigest().encode("ascii")


def _walk_source_files(root: Path) -> Iterable[Path]:
    """Yield source files without materializing or following the whole tree."""

    def fail_walk(error: OSError) -> None:
        raise RepositorySnapshotError(
            "The repository tree could not be read safely."
        ) from error

    for directory, directory_names, file_names in os.walk(
        root,
        topdown=True,
        onerror=fail_walk,
        followlinks=False,
    ):
        directory_path = Path(directory)
        # Prune vendor/generated and linked directories before os.walk can
        # descend into them. Sorting keeps the evidence deterministic without
        # first allocating an unbounded list of every path in the repository.
        directory_names[:] = sorted(
            name
            for name in directory_names
            if name.lower() not in _IGNORED_DIRECTORIES
            and not (directory_path / name).is_symlink()
        )
        for name in sorted(file_names):
            yield directory_path / name


def collect_repository_snapshot(
    repo_path: str | Path,
    *,
    max_files: int = MAX_FILES,
    max_total_bytes: int = MAX_TOTAL_BYTES,
) -> RepositorySnapshot:
    """Collect deterministic, bounded evidence from one repository root."""

    root = Path(repo_path).resolve(strict=True)
    if not root.is_dir():
        raise RepositorySnapshotError("The repository snapshot target is not a directory.")
    if max_files < 1 or max_total_bytes < 1:
        raise ValueError("Repository snapshot bounds must be positive.")

    files: dict[str, bytes] = {}
    environment_names: set[str] = set()
    represented_bytes = 0
    for candidate in _walk_source_files(root):
        try:
            relative = candidate.relative_to(root)
        except ValueError as error:  # pragma: no cover - resolve/root invariant
            raise RepositorySnapshotError("Repository path escaped its source root.") from error
        if candidate.is_symlink() or not candidate.is_file():
            continue
        if len(files) >= max_files:
            raise RepositorySnapshotError(
                f"Repository contains more than the supported {max_files} source files."
            )

        normalized = relative.as_posix()
        try:
            size = candidate.stat().st_size
            if _is_environment_file(candidate):
                raw = candidate.read_bytes()[:MAX_INLINE_FILE_BYTES]
                environment_names.update(_extract_environment_names(raw))
                content = b""
            elif size <= MAX_INLINE_FILE_BYTES:
                content = candidate.read_bytes()
            else:
                content = _large_file_marker(candidate)
        except OSError as error:
            raise RepositorySnapshotError(
                f"Repository file could not be read: {normalized}."
            ) from error
        represented_bytes += len(content)
        if represented_bytes > max_total_bytes:
            raise RepositorySnapshotError(
                "Repository evidence exceeds the bounded change-detection limit."
            )
        files[normalized] = content

    ordered_files = dict(sorted(files.items()))
    return RepositorySnapshot(
        files=ordered_files,
        paths=tuple(ordered_files),
        environment_variable_names=tuple(sorted(environment_names)),
        file_count=len(files),
        represented_bytes=represented_bytes,
    )
