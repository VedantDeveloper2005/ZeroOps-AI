"""Small interfaces that keep safety controls testable without Azure."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from worker.contracts import BundleReference, ExecutionEnvelope, SavedPlanReference


@dataclass(frozen=True)
class SanitizedArtifactReference:
    """User-visible, content-addressed artifact metadata.

    This intentionally has no URI, SAS, ETag, or executor-storage locator.
    """

    artifact_id: str
    kind: str
    sha256: str
    storage_container: str
    storage_path: str
    size_bytes: int
    content_type: str = "application/json"
    access_scope: str = "user"
    sanitization_status: str = "sanitized"
    blob_version_id: str | None = None


class ArtifactStore(Protocol):
    def download_bundle(self, reference: BundleReference, destination: Path) -> None:
        """Download a tenant bundle only if its ETag and digest match."""

    def save_private_plan(
        self,
        envelope: ExecutionEnvelope,
        plan_path: Path,
        plan_sha256: str,
    ) -> SavedPlanReference:
        """Persist a saved plan to executor-only storage."""

    def download_private_plan(
        self,
        reference: SavedPlanReference,
        destination: Path,
    ) -> None:
        """Download the exact executor-only saved plan."""

    def save_sanitized_result(
        self,
        envelope: ExecutionEnvelope,
        result: dict[str, Any],
    ) -> SanitizedArtifactReference:
        """Persist safe history metadata and return its bounded reference."""

    def was_completed(self, envelope: ExecutionEnvelope) -> bool:
        """Return whether an immutable completion receipt exists."""

    def mark_completed(
        self,
        envelope: ExecutionEnvelope,
        result: dict[str, Any],
    ) -> None:
        """Write a completion receipt after the cloud operation settles."""


class StateLease(Protocol):
    def __enter__(self) -> "StateLease":
        ...

    def __exit__(self, exc_type, exc, traceback) -> None:
        ...


class StateLeaseFactory(Protocol):
    def for_envelope(self, envelope: ExecutionEnvelope) -> StateLease:
        ...


class ScaleInProtection(Protocol):
    def protect(self) -> None:
        """Protect this exact VMSS instance before locking or applying."""

    def release(self) -> None:
        """Release protection after settlement and durable result storage."""


class EventSink(Protocol):
    def publish(self, envelope: ExecutionEnvelope, result: dict[str, Any]) -> None:
        """Publish a sanitized workflow event."""
