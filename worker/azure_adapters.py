"""Managed-identity Azure adapters for executor-only data and coordination."""

from __future__ import annotations

import hashlib
import json
import threading
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import quote, urlparse

from azure.core import MatchConditions
from azure.core.exceptions import ResourceExistsError
from azure.servicebus import ServiceBusMessage
from azure.storage.blob import (
    BlobClient,
    BlobLeaseClient,
    BlobServiceClient,
    ContentSettings,
)

from worker.contracts import (
    BundleReference,
    ExecutionEnvelope,
    SavedPlanReference,
    TENANT_CONTAINER_PATTERN,
    USER_ARTIFACT_PATH_PATTERN,
    canonical_digest,
)
from worker.execution_gate import ExecutionGateError, verify_file_digest
from worker.history_events import build_workflow_event
from worker.interfaces import SanitizedArtifactReference


_IMDS_COMPUTE_URL = (
    "http://169.254.169.254/metadata/instance/compute"
    "?api-version=2021-02-01"
)
_ARM_MANAGEMENT_HOST = "management.azure.com"
_ARM_API_VERSION = "2024-11-01"


def _validated_origin_url(url: str, *, scheme: str, hostname: str) -> str:
    """Require an exact origin and reject credentials, ports, and URL smuggling."""
    if not isinstance(url, str) or not url:
        raise ExecutionGateError("Azure request URL is invalid.")
    parsed = urlparse(url)
    try:
        port = parsed.port
    except ValueError as error:
        raise ExecutionGateError("Azure request URL has an invalid port.") from error
    if (
        parsed.scheme != scheme
        or parsed.hostname != hostname
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.fragment
        or not parsed.path.startswith("/")
        or parsed.path.startswith("//")
        or "\\" in parsed.path
        or any(ord(character) < 32 for character in url)
    ):
        raise ExecutionGateError("Azure request URL is outside the approved origin.")
    return url


def _validated_imds_compute_url(url: str) -> str:
    _validated_origin_url(url, scheme="http", hostname="169.254.169.254")
    if url != _IMDS_COMPUTE_URL:
        raise ExecutionGateError("VM metadata request is outside the approved endpoint.")
    return url


def _validated_arm_resource_url(url: str) -> str:
    _validated_origin_url(url, scheme="https", hostname=_ARM_MANAGEMENT_HOST)
    parsed = urlparse(url)
    segments = parsed.path.split("/")
    if (
        len(segments) != 9
        or segments[0] != ""
        or segments[1] != "subscriptions"
        or not segments[2]
        or segments[3] != "resourceGroups"
        or not segments[4]
        or segments[5:8] != ["providers", "Microsoft.Compute", "virtualMachines"]
        or not segments[8]
        or parsed.params
        or parsed.query != f"api-version={_ARM_API_VERSION}"
    ):
        raise ExecutionGateError("ARM request is outside the approved VM endpoint.")
    return url


class _RejectAzureRedirects(urllib.request.HTTPRedirectHandler):
    """Azure control-plane and IMDS calls must never redirect."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise urllib.error.URLError("Azure endpoint redirects are not permitted.")


def _open_approved_azure_request(request, *, timeout: int, validator):
    """Open one prevalidated Azure URL and verify the response did not move."""
    initial_url = validator(request.full_url)
    opener = urllib.request.build_opener(_RejectAzureRedirects())
    response = opener.open(request, timeout=timeout)
    final_url = response.geturl() if hasattr(response, "geturl") else initial_url
    try:
        if final_url != initial_url:
            raise ExecutionGateError("Azure endpoint redirects are not permitted.")
        validator(final_url)
    except Exception:
        response.close()
        raise
    return response


def _encoded_arm_segment(value: str, *, label: str, maximum_length: int) -> str:
    """Encode an IMDS identifier as one ARM path segment."""
    if (
        not isinstance(value, str)
        or not value
        or len(value) > maximum_length
        or value in {".", ".."}
        or any(ord(character) < 32 for character in value)
    ):
        raise ExecutionGateError(f"VM metadata contains an invalid {label}.")
    return quote(value, safe="")


class AzureBlobArtifactStore:
    """Keep user-safe artifacts and executor-only plans in separate accounts."""

    def __init__(
        self,
        *,
        credential,
        artifact_account_name: str,
        executor_account_name: str,
        plan_container_name: str,
    ):
        self.credential = credential
        self.artifact_account_name = artifact_account_name
        self.executor_account_name = executor_account_name
        self.plan_container_name = plan_container_name
        self.artifact_service = BlobServiceClient(
            account_url=f"https://{artifact_account_name}.blob.core.windows.net",
            credential=credential,
        )
        self.executor_service = BlobServiceClient(
            account_url=f"https://{executor_account_name}.blob.core.windows.net",
            credential=credential,
        )

    def _assert_artifact_uri(self, uri: str) -> tuple[str, str]:
        parsed = urlparse(uri)
        if (
            parsed.scheme != "https"
            or parsed.hostname
            != f"{self.artifact_account_name}.blob.core.windows.net"
            or parsed.username
            or parsed.password
            or parsed.port
            or parsed.query
            or parsed.fragment
            or not parsed.path.startswith("/")
            or parsed.path.startswith("//")
            or "%" in parsed.path
        ):
            raise ExecutionGateError("Bundle references an unapproved storage account.")
        path = parsed.path[1:].split("/", 1)
        if (
            len(path) != 2
            or not TENANT_CONTAINER_PATTERN.fullmatch(path[0])
            or not USER_ARTIFACT_PATH_PATTERN.fullmatch(path[1])
        ):
            raise ExecutionGateError(
                "Bundle references a noncanonical tenant artifact."
            )
        return path[0], path[1]

    @staticmethod
    def _download(
        client: BlobClient,
        destination: Path,
        *,
        etag: str,
    ) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with destination.open("xb") as output:
            downloader = client.download_blob(
                etag=etag,
                match_condition=MatchConditions.IfNotModified,
                max_concurrency=4,
            )
            downloader.readinto(output)

    def download_bundle(self, reference: BundleReference, destination: Path) -> None:
        self._assert_artifact_uri(reference.uri)
        client = BlobClient.from_blob_url(reference.uri, credential=self.credential)
        self._download(client, destination, etag=reference.etag)
        verify_file_digest(destination, reference.sha256, label="Terraform bundle")

    def save_private_plan(
        self,
        envelope: ExecutionEnvelope,
        plan_path: Path,
        plan_sha256: str,
    ) -> SavedPlanReference:
        blob_name = (
            f"tenants/{envelope.tenant_id}/workflows/{envelope.workflow_id}/"
            f"plans/{envelope.job_id}/{plan_sha256}.tfplan"
        )
        client = self.executor_service.get_blob_client(
            container=self.plan_container_name,
            blob=blob_name,
        )
        metadata = {
            "sha256": plan_sha256,
            "plan_job_digest": envelope.job_digest,
            "bundle_sha256": envelope.bundle.sha256,
        }
        try:
            with plan_path.open("rb") as stream:
                client.upload_blob(
                    stream,
                    overwrite=False,
                    metadata=metadata,
                    content_settings=ContentSettings(
                        content_type="application/octet-stream",
                        cache_control="no-store",
                    ),
                )
        except ResourceExistsError:
            existing = client.get_blob_properties()
            if existing.metadata != metadata:
                raise ExecutionGateError("Saved plan path is not immutable.")
        properties = client.get_blob_properties()
        return SavedPlanReference(
            blob_name=blob_name,
            etag=properties.etag,
            sha256=plan_sha256,
            plan_job_digest=envelope.job_digest,
            bundle_sha256=envelope.bundle.sha256,
        )

    def download_private_plan(
        self,
        reference: SavedPlanReference,
        destination: Path,
    ) -> None:
        client = self.executor_service.get_blob_client(
            container=self.plan_container_name,
            blob=reference.blob_name,
        )
        self._download(client, destination, etag=reference.etag)
        verify_file_digest(destination, reference.sha256, label="Saved plan")

    def save_sanitized_result(
        self,
        envelope: ExecutionEnvelope,
        result: dict[str, Any],
    ) -> SanitizedArtifactReference:
        tenant_container, _ = self._assert_artifact_uri(envelope.bundle.uri)
        encoded = json.dumps(
            result,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        ).encode("utf-8")
        digest = hashlib.sha256(encoded).hexdigest()
        artifact_id = str(
            uuid.uuid5(
                uuid.UUID(envelope.job_id),
                f"zeroops:{envelope.operation}:sanitized-result",
            )
        )
        blob_name = f"objects/{artifact_id}/v1/{digest}"
        client = self.artifact_service.get_blob_client(
            container=tenant_container,
            blob=blob_name,
        )
        metadata = {
            "sha256": digest,
            "sanitization_status": "sanitized",
        }
        try:
            client.upload_blob(
                encoded,
                overwrite=False,
                metadata=metadata,
                content_settings=ContentSettings(
                    content_type="application/json",
                    cache_control="no-store",
                ),
            )
        except ResourceExistsError:
            existing = client.get_blob_properties()
            if existing.metadata != metadata:
                raise ExecutionGateError("Sanitized result path is not immutable.")
        return SanitizedArtifactReference(
            artifact_id=artifact_id,
            kind=(
                "terraform-plan-summary"
                if envelope.operation == "plan"
                else "terraform-apply-receipt"
            ),
            sha256=digest,
            storage_container=tenant_container,
            storage_path=blob_name,
            size_bytes=len(encoded),
        )

    def _receipt_client(self, envelope: ExecutionEnvelope) -> BlobClient:
        blob_name = (
            f"receipts/{envelope.tenant_id}/{envelope.workflow_id}/"
            f"{envelope.job_digest}.json"
        )
        return self.executor_service.get_blob_client(
            container=self.plan_container_name,
            blob=blob_name,
        )

    def was_completed(self, envelope: ExecutionEnvelope) -> bool:
        return self._receipt_client(envelope).exists()

    def mark_completed(
        self,
        envelope: ExecutionEnvelope,
        result: dict[str, Any],
    ) -> None:
        receipt = {
            "schema_version": "1.0",
            "job_digest": envelope.job_digest,
            "operation": envelope.operation,
            "status": result.get("status"),
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "result_digest": canonical_digest(result),
        }
        plan_handle = result.get("plan_handle")
        if envelope.operation == "plan" and isinstance(plan_handle, Mapping):
            fields = (
                "blob_name",
                "etag",
                "sha256",
                "plan_job_digest",
                "bundle_sha256",
            )
            if all(
                isinstance(plan_handle.get(field), str)
                and bool(plan_handle[field])
                for field in fields
            ):
                # This is intentionally durable only in executor storage. It
                # is never supplied to the user-history event builder.
                receipt["control_result"] = {
                    "saved_plan": {
                        field: plan_handle[field]
                        for field in fields
                    }
                }
        encoded = json.dumps(
            receipt,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        client = self._receipt_client(envelope)
        try:
            client.upload_blob(
                encoded,
                overwrite=False,
                metadata={"sha256": hashlib.sha256(encoded).hexdigest()},
                content_settings=ContentSettings(
                    content_type="application/json",
                    cache_control="no-store",
                ),
            )
        except ResourceExistsError:
            # A completion receipt is immutable and makes duplicate queue
            # delivery safe. Existing means the operation already settled.
            return


class AzureBlobStateLease:
    """Independent job lease in addition to Terraform's native state lock."""

    def __init__(self, blob_client: BlobClient):
        self.blob_client = blob_client
        self.lease: BlobLeaseClient | None = None
        self.stop_event = threading.Event()
        self.renewal_error: BaseException | None = None
        self.thread: threading.Thread | None = None

    def __enter__(self) -> "AzureBlobStateLease":
        try:
            self.blob_client.upload_blob(
                b"",
                overwrite=False,
                content_settings=ContentSettings(
                    content_type="application/octet-stream",
                    cache_control="no-store",
                ),
            )
        except ResourceExistsError:
            pass
        self.lease = BlobLeaseClient(self.blob_client)
        self.lease.acquire(lease_duration=60)

        def renew() -> None:
            while not self.stop_event.wait(20):
                try:
                    assert self.lease is not None
                    self.lease.renew()
                except BaseException as error:  # surfaced after the tool boundary
                    self.renewal_error = error
                    return

        self.thread = threading.Thread(target=renew, name="state-lease", daemon=True)
        self.thread.start()
        return self

    def assert_current(self) -> None:
        if self.renewal_error is not None:
            raise ExecutionGateError("Executor state lease was lost.")

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.stop_event.set()
        if self.thread is not None:
            self.thread.join(timeout=5)
        try:
            if self.lease is not None:
                self.lease.release()
        finally:
            if exc is None:
                self.assert_current()


class AzureBlobStateLeaseFactory:
    def __init__(
        self,
        *,
        credential,
        executor_account_name: str,
        state_container_name: str,
    ):
        self.service = BlobServiceClient(
            account_url=f"https://{executor_account_name}.blob.core.windows.net",
            credential=credential,
        )
        self.state_container_name = state_container_name

    def for_envelope(self, envelope: ExecutionEnvelope) -> AzureBlobStateLease:
        key_digest = hashlib.sha256(envelope.state_key.encode("utf-8")).hexdigest()
        blob_name = f"leases/{envelope.tenant_id}/{key_digest}.lock"
        return AzureBlobStateLease(
            self.service.get_blob_client(
                container=self.state_container_name,
                blob=blob_name,
            )
        )


class VmssScaleInProtection:
    """Protect the current Flexible VMSS VM through ARM while it owns work."""

    IMDS_URL = _IMDS_COMPUTE_URL

    def __init__(self, credential):
        self.credential = credential
        self._metadata: dict[str, str] | None = None

    def _compute_metadata(self) -> dict[str, str]:
        if self._metadata is not None:
            return self._metadata
        request = urllib.request.Request(
            self.IMDS_URL,
            headers={"Metadata": "true"},
            method="GET",
        )
        try:
            with _open_approved_azure_request(
                request,
                timeout=5,
                validator=_validated_imds_compute_url,
            ) as response:
                document = json.loads(response.read())
        except (OSError, urllib.error.URLError, json.JSONDecodeError) as error:
            raise ExecutionGateError("VM instance metadata is unavailable.") from error
        required = ["subscriptionId", "resourceGroupName", "name"]
        if not isinstance(document, dict) or any(
            not isinstance(document.get(key), str) or not document[key]
            for key in required
        ):
            raise ExecutionGateError("VM instance metadata is incomplete.")
        self._metadata = {key: document[key] for key in required}
        return self._metadata

    def _set(self, protected: bool) -> None:
        metadata = self._compute_metadata()
        token = self.credential.get_token(
            "https://management.azure.com/.default"
        ).token
        subscription_id = _encoded_arm_segment(
            metadata["subscriptionId"], label="subscription ID", maximum_length=64
        )
        resource_group = _encoded_arm_segment(
            metadata["resourceGroupName"], label="resource group", maximum_length=90
        )
        virtual_machine = _encoded_arm_segment(
            metadata["name"], label="virtual machine name", maximum_length=64
        )
        resource_url = _validated_arm_resource_url(
            "https://management.azure.com/subscriptions/"
            f"{subscription_id}/resourceGroups/"
            f"{resource_group}/providers/Microsoft.Compute/"
            f"virtualMachines/{virtual_machine}?api-version={_ARM_API_VERSION}"
        )
        body = json.dumps(
            {
                "properties": {
                    "protectionPolicy": {
                        "protectFromScaleIn": protected,
                        "protectFromScaleSetActions": False,
                    }
                }
            }
        ).encode("utf-8")
        request = urllib.request.Request(
            resource_url,
            data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="PATCH",
        )
        try:
            with _open_approved_azure_request(
                request,
                timeout=30,
                validator=_validated_arm_resource_url,
            ) as response:
                if response.status not in {200, 201, 202}:
                    raise ExecutionGateError("VMSS scale-in protection update failed.")
        except (OSError, urllib.error.URLError) as error:
            raise ExecutionGateError("VMSS scale-in protection update failed.") from error

    def protect(self) -> None:
        self._set(True)

    def release(self) -> None:
        self._set(False)


class ServiceBusEventSink:
    def __init__(self, service_bus_client, queue_name: str):
        self.service_bus_client = service_bus_client
        self.queue_name = queue_name

    def publish(self, envelope: ExecutionEnvelope, result: dict[str, Any]) -> None:
        event = build_workflow_event(envelope, result)
        body = json.dumps(
            event,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
            allow_nan=False,
        )
        message = ServiceBusMessage(
            body,
            content_type="application/json",
            message_id=event["event_id"],
            correlation_id=envelope.workflow_id,
        )
        with self.service_bus_client.get_queue_sender(
            queue_name=self.queue_name
        ) as sender:
            sender.send_messages(message)
