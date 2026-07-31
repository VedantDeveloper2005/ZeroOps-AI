"""Managed-identity Blob access with digest and endpoint verification."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import BlobServiceClient, ContentSettings

from .contracts import ArtifactReferenceV1
from .security import canonical_json_bytes, sha256_bytes


@dataclass(frozen=True)
class UploadedArtifact:
    version_id: str | None
    etag: str | None
    sha256: str
    size_bytes: int


class BlobArtifactStore:
    def __init__(self, account_url: str, credential: Any):
        self.account_url = account_url.rstrip("/")
        if not self.account_url.startswith("https://"):
            raise ValueError("Blob account URL must use HTTPS")
        self._client = BlobServiceClient(account_url=self.account_url, credential=credential)

    def _assert_account(self, artifact: ArtifactReferenceV1) -> None:
        if artifact.account_url.rstrip("/").lower() != self.account_url.lower():
            raise PermissionError("Artifact account is outside this workload boundary")

    def download_verified(
        self,
        artifact: ArtifactReferenceV1,
        *,
        maximum_bytes: int,
    ) -> bytes:
        self._assert_account(artifact)
        if artifact.size_bytes > maximum_bytes:
            raise ValueError("Artifact exceeds the worker input limit")
        blob = self._client.get_blob_client(
            container=artifact.container,
            blob=artifact.blob_name,
            version_id=artifact.version_id,
        )
        properties = blob.get_blob_properties()
        if properties.size > maximum_bytes or properties.size != artifact.size_bytes:
            raise ValueError("Artifact size does not match its immutable reference")
        body = blob.download_blob(max_concurrency=2).readall()
        if len(body) != artifact.size_bytes or sha256_bytes(body) != artifact.sha256:
            raise ValueError("Artifact digest verification failed")
        return body

    def download_verified_json(
        self,
        artifact: ArtifactReferenceV1,
        *,
        maximum_bytes: int,
    ) -> dict[str, Any]:
        body = self.download_verified(artifact, maximum_bytes=maximum_bytes)
        value = json.loads(body.decode("utf-8"))
        if not isinstance(value, dict):
            raise ValueError("Artifact JSON root must be an object")
        return value

    def upload_immutable_json(
        self,
        *,
        container: str,
        blob_name: str,
        value: Any,
        metadata: dict[str, str],
    ) -> UploadedArtifact:
        body = canonical_json_bytes(value)
        return self.upload_immutable_bytes(
            container=container,
            blob_name=blob_name,
            body=body,
            media_type="application/json",
            metadata=metadata,
        )

    def upload_immutable_bytes(
        self,
        *,
        container: str,
        blob_name: str,
        body: bytes,
        media_type: str,
        metadata: dict[str, str],
    ) -> UploadedArtifact:
        if not body:
            raise ValueError("Immutable artifacts cannot be empty")
        if not media_type or len(media_type) > 128:
            raise ValueError("Artifact media type is invalid")
        digest = sha256_bytes(body)
        blob = self._client.get_blob_client(container=container, blob=blob_name)
        safe_metadata = {
            str(key).lower().replace("_", "-")[:128]: str(item)[:1024]
            for key, item in metadata.items()
        }
        safe_metadata["sha256"] = digest
        try:
            blob.upload_blob(
                body,
                overwrite=False,
                metadata=safe_metadata,
                content_settings=ContentSettings(content_type=media_type),
            )
        except ResourceExistsError:
            existing = blob.get_blob_properties()
            if (
                (existing.metadata or {}).get("sha256") != digest
                or existing.size != len(body)
            ):
                raise ValueError("Immutable artifact path already contains different content")
            existing_body = blob.download_blob(max_concurrency=2).readall()
            if len(existing_body) != len(body) or sha256_bytes(existing_body) != digest:
                raise ValueError("Immutable artifact path failed content verification")
        properties = blob.get_blob_properties()
        etag = str(getattr(properties, "etag", ""))
        if not etag:
            raise ValueError("Immutable artifact upload did not return a storage ETag")
        return UploadedArtifact(
            version_id=getattr(properties, "version_id", None),
            etag=etag,
            sha256=digest,
            size_bytes=len(body),
        )
