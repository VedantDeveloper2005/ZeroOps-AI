"""Tenant-isolated immutable artifact storage.

Production uses Azure Blob Storage with Microsoft Entra authentication only.
The local filesystem adapter exists exclusively for focused tests; application
configuration never selects it automatically.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

try:
    from backend import config, models
    from backend.services.redaction import (
        redact_sensitive_values,
        safe_download_filename,
        sanitize_artifact_content,
    )
    from backend.services.tenancy import require_tenant_membership
except ImportError:
    import config
    import models
    from services.redaction import redact_sensitive_values, safe_download_filename, sanitize_artifact_content
    from services.tenancy import require_tenant_membership


_BLOB_PATH_PATTERN = re.compile(
    r"^objects/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/v[1-9][0-9]*/[0-9a-f]{64}$"
)
_DIGEST_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_EXECUTOR_ONLY_KINDS = {
    "raw_terraform_plan",
    "terraform_state",
    "terraform_state_backup",
}


class ArtifactIntegrityError(RuntimeError):
    pass


class ArtifactStoreUnavailable(RuntimeError):
    pass


@dataclass(frozen=True)
class ArtifactLocation:
    container: str
    path: str


def opaque_tenant_container(tenant_id: uuid.UUID, namespace_key: str) -> str:
    """Derive a stable Blob container name that does not expose a tenant UUID."""

    if len(namespace_key.encode("utf-8")) < 32:
        raise ValueError("The artifact namespace key must contain at least 32 bytes.")
    digest = hmac.new(
        namespace_key.encode("utf-8"),
        str(tenant_id).encode("ascii"),
        hashlib.sha256,
    ).hexdigest()[:40]
    return f"t-{digest}"


def immutable_blob_path(artifact_id: uuid.UUID, version: int, sha256_digest: str) -> str:
    if version < 1:
        raise ValueError("Artifact version must be at least 1.")
    if not _DIGEST_PATTERN.fullmatch(sha256_digest):
        raise ValueError("Artifact digest must be a lowercase SHA-256 value.")
    return f"objects/{artifact_id}/v{version}/{sha256_digest}"


class ArtifactStore(ABC):
    def __init__(self, *, namespace_key: str, max_download_bytes: int) -> None:
        if max_download_bytes < 1:
            raise ValueError("max_download_bytes must be positive.")
        self._namespace_key = namespace_key
        self.max_download_bytes = max_download_bytes

    def container_for_tenant(self, tenant_id: uuid.UUID) -> str:
        return opaque_tenant_container(tenant_id, self._namespace_key)

    def validate_location(self, tenant_id: uuid.UUID, location: ArtifactLocation) -> None:
        if not hmac.compare_digest(location.container, self.container_for_tenant(tenant_id)):
            raise ArtifactIntegrityError("Artifact tenant container mismatch.")
        if not _BLOB_PATH_PATTERN.fullmatch(location.path):
            raise ArtifactIntegrityError("Artifact storage path is invalid.")

    @abstractmethod
    async def put_immutable(
        self,
        *,
        tenant_id: uuid.UUID,
        location: ArtifactLocation,
        data: bytes,
        content_type: str,
        sha256_digest: str,
        metadata: dict[str, str],
    ) -> None:
        raise NotImplementedError

    @abstractmethod
    async def read_verified(
        self,
        *,
        tenant_id: uuid.UUID,
        location: ArtifactLocation,
        expected_digest: str,
        expected_size: int,
    ) -> bytes:
        raise NotImplementedError

    @abstractmethod
    async def delete(self, *, tenant_id: uuid.UUID, location: ArtifactLocation) -> None:
        raise NotImplementedError


class AzureBlobArtifactStore(ArtifactStore):
    """Azure Blob implementation authenticated with a managed identity."""

    def __init__(
        self,
        *,
        account_url: str,
        namespace_key: str,
        max_download_bytes: int,
        managed_identity_client_id: Optional[str] = None,
    ) -> None:
        super().__init__(namespace_key=namespace_key, max_download_bytes=max_download_bytes)
        if not account_url.lower().startswith("https://") or not account_url.lower().endswith(
            ".blob.core.windows.net"
        ):
            raise ValueError("Artifact storage account URL must be an Azure Blob HTTPS endpoint.")

        # Imports remain lazy so unit tests can run without contacting Azure.
        from azure.identity.aio import DefaultAzureCredential, ManagedIdentityCredential
        from azure.storage.blob.aio import BlobServiceClient

        if managed_identity_client_id:
            credential = ManagedIdentityCredential(client_id=managed_identity_client_id)
        else:
            credential = DefaultAzureCredential(exclude_interactive_browser_credential=True)
        self._credential = credential
        self._service = BlobServiceClient(account_url=account_url, credential=credential)

    async def put_immutable(
        self,
        *,
        tenant_id: uuid.UUID,
        location: ArtifactLocation,
        data: bytes,
        content_type: str,
        sha256_digest: str,
        metadata: dict[str, str],
    ) -> None:
        from azure.core.exceptions import ResourceExistsError
        from azure.storage.blob import ContentSettings

        self.validate_location(tenant_id, location)
        actual_digest = hashlib.sha256(data).hexdigest()
        if not hmac.compare_digest(actual_digest, sha256_digest):
            raise ArtifactIntegrityError("Artifact digest did not match its content.")

        container = self._service.get_container_client(location.container)
        try:
            await container.create_container()
        except ResourceExistsError:
            pass

        blob = container.get_blob_client(location.path)
        await blob.upload_blob(
            data,
            overwrite=False,
            metadata={key: str(value)[:256] for key, value in metadata.items()},
            content_settings=ContentSettings(content_type=content_type),
        )

    async def read_verified(
        self,
        *,
        tenant_id: uuid.UUID,
        location: ArtifactLocation,
        expected_digest: str,
        expected_size: int,
    ) -> bytes:
        self.validate_location(tenant_id, location)
        if expected_size < 0 or expected_size > self.max_download_bytes:
            raise ArtifactIntegrityError("Artifact exceeds the download size limit.")

        blob = self._service.get_blob_client(location.container, location.path)
        properties = await blob.get_blob_properties()
        if properties.size != expected_size or properties.size > self.max_download_bytes:
            raise ArtifactIntegrityError("Artifact size metadata did not match Blob Storage.")
        data = await (await blob.download_blob()).readall()
        digest = hashlib.sha256(data).hexdigest()
        if not hmac.compare_digest(digest, expected_digest):
            raise ArtifactIntegrityError("Artifact failed its SHA-256 integrity check.")
        return data

    async def delete(self, *, tenant_id: uuid.UUID, location: ArtifactLocation) -> None:
        from azure.core.exceptions import ResourceNotFoundError

        self.validate_location(tenant_id, location)
        try:
            await self._service.get_blob_client(location.container, location.path).delete_blob()
        except ResourceNotFoundError:
            return


class LocalFilesystemArtifactStore(ArtifactStore):
    """Explicit test double. Never selected by runtime configuration."""

    def __init__(
        self,
        *,
        root: Path,
        namespace_key: str = "zeroops-test-only-namespace-key-32",
        max_download_bytes: int = 25 * 1024 * 1024,
    ) -> None:
        super().__init__(namespace_key=namespace_key, max_download_bytes=max_download_bytes)
        self._root = root.resolve()
        self._root.mkdir(parents=True, exist_ok=True)

    def _file_path(self, location: ArtifactLocation) -> Path:
        candidate = (self._root / location.container / Path(*location.path.split("/"))).resolve()
        if self._root not in candidate.parents:
            raise ArtifactIntegrityError("Artifact path escaped the configured test root.")
        return candidate

    async def put_immutable(
        self,
        *,
        tenant_id: uuid.UUID,
        location: ArtifactLocation,
        data: bytes,
        content_type: str,
        sha256_digest: str,
        metadata: dict[str, str],
    ) -> None:
        del content_type, metadata
        self.validate_location(tenant_id, location)
        if hashlib.sha256(data).hexdigest() != sha256_digest:
            raise ArtifactIntegrityError("Artifact digest did not match its content.")
        path = self._file_path(location)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("xb") as output:
            output.write(data)

    async def read_verified(
        self,
        *,
        tenant_id: uuid.UUID,
        location: ArtifactLocation,
        expected_digest: str,
        expected_size: int,
    ) -> bytes:
        self.validate_location(tenant_id, location)
        if expected_size < 0 or expected_size > self.max_download_bytes:
            raise ArtifactIntegrityError("Artifact exceeds the download size limit.")
        data = self._file_path(location).read_bytes()
        if len(data) != expected_size:
            raise ArtifactIntegrityError("Artifact size metadata did not match storage.")
        if not hmac.compare_digest(hashlib.sha256(data).hexdigest(), expected_digest):
            raise ArtifactIntegrityError("Artifact failed its SHA-256 integrity check.")
        return data

    async def delete(self, *, tenant_id: uuid.UUID, location: ArtifactLocation) -> None:
        self.validate_location(tenant_id, location)
        path = self._file_path(location)
        if path.exists():
            path.unlink()


@lru_cache(maxsize=1)
def get_artifact_store() -> ArtifactStore:
    """Build the production store; intentionally has no filesystem fallback."""

    account_url = config.ARTIFACT_STORAGE_ACCOUNT_URL.strip()
    namespace_key = config.ARTIFACT_STORAGE_NAMESPACE_KEY
    if not account_url or not namespace_key:
        raise ArtifactStoreUnavailable(
            "Azure artifact storage is not configured. Set its account URL and namespace key in Key Vault."
        )
    return AzureBlobArtifactStore(
        account_url=account_url,
        namespace_key=namespace_key,
        managed_identity_client_id=config.ARTIFACT_STORAGE_MANAGED_IDENTITY_CLIENT_ID or None,
        max_download_bytes=config.ARTIFACT_STORAGE_MAX_DOWNLOAD_MB * 1024 * 1024,
    )


async def persist_user_artifact(
    db: AsyncSession,
    *,
    store: ArtifactStore,
    tenant_id: uuid.UUID,
    operation_run_id: uuid.UUID,
    created_by_user_id: uuid.UUID,
    kind: str,
    display_name: str,
    content_type: str,
    data: bytes,
    project_id: Optional[uuid.UUID] = None,
    artifact_key: Optional[uuid.UUID] = None,
    version: int = 1,
    metadata: Optional[dict[str, Any]] = None,
) -> models.Artifact:
    """Sanitize, upload, and index one immutable user-visible artifact."""

    normalized_kind = kind.strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", normalized_kind):
        raise ValueError("Artifact kind must be a lowercase identifier of at most 64 characters.")
    if normalized_kind in _EXECUTOR_ONLY_KINDS:
        raise ValueError("Terraform state and raw plan artifacts require executor-only storage.")
    if version < 1:
        raise ValueError("Artifact version must be at least 1.")
    await require_tenant_membership(
        db,
        user_id=created_by_user_id,
        tenant_id=tenant_id,
    )
    run_result = await db.execute(
        select(models.OperationRun).where(
            and_(
                models.OperationRun.id == operation_run_id,
                models.OperationRun.tenant_id == tenant_id,
            )
        )
    )
    operation_run = run_result.scalars().first()
    if operation_run is None:
        raise ValueError("Operation run does not belong to the selected tenant.")
    if project_id is not None and operation_run.project_id not in {None, project_id}:
        raise ValueError("Artifact project does not match the operation run.")

    normalized_content_type = content_type.split(";", 1)[0].strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9.+-]*/[a-z0-9][a-z0-9.+-]*", normalized_content_type):
        raise ValueError("Artifact content type is invalid.")
    sanitized = sanitize_artifact_content(data, normalized_content_type)
    if len(sanitized) > store.max_download_bytes:
        raise ValueError("Artifact exceeds the configured user-download size limit.")
    digest = hashlib.sha256(sanitized).hexdigest()
    artifact_id = uuid.uuid4()
    artifact_key = artifact_key or uuid.uuid4()
    location = ArtifactLocation(
        container=store.container_for_tenant(tenant_id),
        path=immutable_blob_path(artifact_id, version, digest),
    )
    clean_metadata = redact_sensitive_values(metadata or {})
    blob_metadata = {
        "artifact_id": str(artifact_id),
        "artifact_key": str(artifact_key),
        "version": str(version),
        "sha256": digest,
    }
    await store.put_immutable(
        tenant_id=tenant_id,
        location=location,
        data=sanitized,
        content_type=normalized_content_type,
        sha256_digest=digest,
        metadata=blob_metadata,
    )

    artifact = models.Artifact(
        id=artifact_id,
        artifact_key=artifact_key,
        tenant_id=tenant_id,
        operation_run_id=operation_run_id,
        project_id=project_id or operation_run.project_id,
        created_by_user_id=created_by_user_id,
        kind=normalized_kind,
        display_name=safe_download_filename(display_name),
        content_type=normalized_content_type,
        storage_container=location.container,
        storage_path=location.path,
        sha256_digest=digest,
        size_bytes=len(sanitized),
        version=version,
        access_scope="user",
        sanitization_status="sanitized",
        artifact_metadata=clean_metadata,
    )
    db.add(artifact)
    try:
        await db.flush()
    except Exception:
        await store.delete(tenant_id=tenant_id, location=location)
        raise
    return artifact


async def read_user_artifact(store: ArtifactStore, artifact: models.Artifact) -> bytes:
    if artifact.access_scope != "user" or artifact.sanitization_status != "sanitized":
        raise ArtifactIntegrityError("Artifact is not approved for user download.")
    return await store.read_verified(
        tenant_id=artifact.tenant_id,
        location=ArtifactLocation(
            container=artifact.storage_container,
            path=artifact.storage_path,
        ),
        expected_digest=artifact.sha256_digest,
        expected_size=artifact.size_bytes,
    )
