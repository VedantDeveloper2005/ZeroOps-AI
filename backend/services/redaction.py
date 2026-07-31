"""Shared redaction helpers for persisted history and user-visible artifacts.

The helpers are intentionally conservative. A history record is evidence, not
an execution payload, so secret-looking values are removed before they can be
written to PostgreSQL or a user-downloadable Blob.
"""

from __future__ import annotations

import json
import re
from pathlib import PurePath
from typing import Any


REDACTED = "<REDACTED>"

_SENSITIVE_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "client_secret",
    "connection_string",
    "cookie",
    "credential",
    "database_url",
    "db_password",
    "github_token",
    "password",
    "private_key",
    "raw_parameters",
    "refresh_token",
    "secret",
    "secret_key",
    "terraform_state",
    "tfstate",
    "token",
}
_SENSITIVE_SUFFIXES = (
    "_api_key",
    "_connection_string",
    "_credential",
    "_password",
    "_private_key",
    "_secret",
    "_token",
)

_AUTHORIZATION_PATTERN = re.compile(
    r"(?i)\b(authorization\s*[:=]\s*(?:bearer|basic)\s+)[^\s,;]+"
)
_URI_CREDENTIAL_PATTERN = re.compile(r"(?i)([a-z][a-z0-9+.-]*://)[^/\s:@]+:[^/\s@]+@")
_ASSIGNMENT_PATTERN = re.compile(
    r"(?im)\b("
    r"(?:api[_-]?key|client[_-]?secret|connection[_-]?string|database[_-]?url|"
    r"password|private[_-]?key|refresh[_-]?token|secret|token)"
    r")(\s*[:=]\s*)([^\s,;]+)"
)


def _normalized_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def is_sensitive_key(key: Any) -> bool:
    normalized = _normalized_key(key)
    return normalized in _SENSITIVE_KEYS or normalized.endswith(_SENSITIVE_SUFFIXES)


def redact_sensitive_values(value: Any) -> Any:
    """Return a JSON-safe structure with secret-like values removed."""

    if isinstance(value, dict):
        return {
            str(key): REDACTED if is_sensitive_key(key) else redact_sensitive_values(item)
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple, set)):
        return [redact_sensitive_values(item) for item in value]
    if isinstance(value, bytes):
        return REDACTED
    if isinstance(value, str):
        return redact_sensitive_text(value)
    if value is None or isinstance(value, (int, float, bool)):
        return value
    return str(value)


def redact_sensitive_text(value: str, *, maximum_length: int = 100_000) -> str:
    """Redact common credential shapes and cap stored diagnostic text."""

    text = str(value or "")[:maximum_length]
    text = _AUTHORIZATION_PATTERN.sub(r"\1" + REDACTED, text)
    text = _URI_CREDENTIAL_PATTERN.sub(r"\1" + REDACTED + "@", text)
    text = _ASSIGNMENT_PATTERN.sub(r"\1\2" + REDACTED, text)
    return text


def sanitize_artifact_content(data: bytes, content_type: str) -> bytes:
    """Sanitize JSON or UTF-8 text intended for user download.

    Binary artifacts are rejected because their contents cannot be reliably
    inspected at this boundary. Executor-only state and raw Terraform plan
    files must use a separate, non-user-downloadable storage account.
    """

    normalized_type = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized_type == "application/json" or normalized_type.endswith("+json"):
        parsed = json.loads(data.decode("utf-8"))
        redacted = redact_sensitive_values(parsed)
        return json.dumps(redacted, sort_keys=True, indent=2, ensure_ascii=False).encode("utf-8")
    if normalized_type.startswith("text/") or normalized_type in {
        "application/hcl",
        "application/x-hcl",
        "application/yaml",
        "application/x-yaml",
    }:
        return redact_sensitive_text(data.decode("utf-8")).encode("utf-8")
    raise ValueError("User-downloadable artifacts must be JSON or UTF-8 text.")


def safe_download_filename(value: str, *, fallback: str = "artifact.txt") -> str:
    """Return a header-safe basename without path or control characters."""

    name = PurePath(str(value or "")).name
    name = re.sub(r"[\x00-\x1f\x7f\"'\\/:;]+", "-", name)
    name = re.sub(r"\s+", " ", name).strip(" .-")
    return name[:160] or fallback
