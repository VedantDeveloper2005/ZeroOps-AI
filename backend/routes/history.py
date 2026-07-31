"""Authenticated tenant-scoped operation history API."""

from __future__ import annotations

import io
import logging
import uuid
from typing import Optional
from urllib.parse import quote

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

try:
    from backend import auth, models, schemas
    from backend.database import get_db
    from backend.services import history as history_service
    from backend.services.artifacts import (
        ArtifactIntegrityError,
        ArtifactStore,
        ArtifactStoreUnavailable,
        get_artifact_store,
        read_user_artifact,
    )
    from backend.services.redaction import safe_download_filename
    from backend.services.tenancy import resolve_tenant
except ImportError:
    import auth
    import models
    import schemas
    from database import get_db
    from services import history as history_service
    from services.artifacts import (
        ArtifactIntegrityError,
        ArtifactStore,
        ArtifactStoreUnavailable,
        get_artifact_store,
        read_user_artifact,
    )
    from services.redaction import safe_download_filename
    from services.tenancy import resolve_tenant


logger = logging.getLogger("zeroops.routes.history")
router = APIRouter(prefix="/api/history", tags=["history"])


def artifact_store_dependency() -> ArtifactStore:
    try:
        return get_artifact_store()
    except ArtifactStoreUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Artifact storage is not available.",
        ) from error


def _run_summary(
    run: models.OperationRun,
    *,
    artifact_count: int,
    event_count: int,
) -> schemas.OperationRunSummaryResponse:
    return schemas.OperationRunSummaryResponse(
        id=run.id,
        tenant_id=run.tenant_id,
        project_id=run.project_id,
        parent_operation_run_id=run.parent_operation_run_id,
        operation_type=run.operation_type,
        status=run.status,
        source_revision=run.source_revision,
        input_digest=run.input_digest,
        summary=run.summary or {},
        model_provider=run.model_provider,
        model_name=run.model_name,
        model_version=run.model_version,
        prompt_version=run.prompt_version,
        input_tokens=run.input_tokens,
        output_tokens=run.output_tokens,
        model_cost_microusd=run.model_cost_microusd,
        error_code=run.error_code,
        redacted_error=run.redacted_error,
        artifact_count=artifact_count,
        event_count=event_count,
        started_at=run.started_at,
        completed_at=run.completed_at,
        created_at=run.created_at,
        updated_at=run.updated_at,
    )


def _artifact_response(artifact: models.Artifact) -> schemas.HistoryArtifactResponse:
    return schemas.HistoryArtifactResponse(
        id=artifact.id,
        artifact_key=artifact.artifact_key,
        kind=artifact.kind,
        display_name=artifact.display_name,
        content_type=artifact.content_type,
        sha256_digest=artifact.sha256_digest,
        size_bytes=artifact.size_bytes,
        version=artifact.version,
        metadata=artifact.artifact_metadata or {},
        created_at=artifact.created_at,
        expires_at=artifact.expires_at,
    )


def _event_response(event: models.ActivityEvent) -> schemas.HistoryActivityEventResponse:
    return schemas.HistoryActivityEventResponse(
        id=event.id,
        action=event.action,
        actor_type=event.actor_type,
        details=event.details,
        event_data=event.event_data or {},
        external_event_id=event.external_event_id,
        sequence_number=event.sequence_number,
        created_at=event.created_at,
    )


@router.get("", response_model=schemas.OperationHistoryPageResponse)
async def list_history(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=25, ge=1, le=100),
    operation_type: Optional[str] = Query(default=None, min_length=1, max_length=64),
    status_value: Optional[str] = Query(default=None, alias="status", min_length=1, max_length=64),
    project_id: Optional[uuid.UUID] = Query(default=None),
    requested_tenant_id: Optional[uuid.UUID] = Header(default=None, alias="X-ZeroOps-Tenant"),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
) -> schemas.OperationHistoryPageResponse:
    tenant = await resolve_tenant(
        db,
        user=current_user,
        requested_tenant_id=requested_tenant_id,
    )
    result = await history_service.list_operation_runs(
        db,
        tenant_id=tenant.id,
        page=page,
        per_page=per_page,
        operation_type=operation_type,
        status_value=status_value,
        project_id=project_id,
    )
    return schemas.OperationHistoryPageResponse(
        items=[
            _run_summary(run, artifact_count=artifact_count, event_count=event_count)
            for run, artifact_count, event_count in result.items
        ],
        page=page,
        per_page=per_page,
        total=result.total,
        has_next=page * per_page < result.total,
    )


@router.get("/{operation_run_id}", response_model=schemas.OperationRunDetailResponse)
async def get_history_detail(
    operation_run_id: uuid.UUID,
    requested_tenant_id: Optional[uuid.UUID] = Header(default=None, alias="X-ZeroOps-Tenant"),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
) -> schemas.OperationRunDetailResponse:
    tenant = await resolve_tenant(
        db,
        user=current_user,
        requested_tenant_id=requested_tenant_id,
    )
    run = await history_service.require_operation_run(
        db,
        tenant_id=tenant.id,
        operation_run_id=operation_run_id,
    )
    events = await history_service.list_operation_events(
        db,
        tenant_id=tenant.id,
        operation_run_id=run.id,
    )
    artifacts = await history_service.list_operation_artifacts(
        db,
        tenant_id=tenant.id,
        operation_run_id=run.id,
    )
    summary = _run_summary(run, artifact_count=len(artifacts), event_count=len(events))
    return schemas.OperationRunDetailResponse(
        **summary.model_dump(),
        events=[_event_response(event) for event in events],
        artifacts=[_artifact_response(artifact) for artifact in artifacts],
    )


@router.get("/{operation_run_id}/artifacts/{artifact_id}/download")
async def download_history_artifact(
    operation_run_id: uuid.UUID,
    artifact_id: uuid.UUID,
    requested_tenant_id: Optional[uuid.UUID] = Header(default=None, alias="X-ZeroOps-Tenant"),
    db: AsyncSession = Depends(get_db),
    current_user: models.User = Depends(auth.get_current_user),
    store: ArtifactStore = Depends(artifact_store_dependency),
) -> StreamingResponse:
    tenant = await resolve_tenant(
        db,
        user=current_user,
        requested_tenant_id=requested_tenant_id,
    )
    # The query binds all three ownership keys. A guessed artifact UUID cannot
    # be used to cross either a tenant or operation-run boundary.
    artifact = await history_service.require_downloadable_artifact(
        db,
        tenant_id=tenant.id,
        operation_run_id=operation_run_id,
        artifact_id=artifact_id,
    )
    try:
        payload = await read_user_artifact(store, artifact)
    except ArtifactIntegrityError as error:
        logger.error("Artifact integrity validation failed for %s: %s", artifact.id, error)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Artifact integrity validation failed.",
        ) from error
    except ArtifactStoreUnavailable as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Artifact storage is not available.",
        ) from error

    filename = safe_download_filename(artifact.display_name)
    encoded_filename = quote(filename, safe="")
    return StreamingResponse(
        io.BytesIO(payload),
        media_type=artifact.content_type,
        headers={
            "Content-Disposition": f"attachment; filename=\"artifact\"; filename*=UTF-8''{encoded_filename}",
            "Content-Length": str(len(payload)),
            "Cache-Control": "private, no-store, max-age=0",
            "X-Content-Type-Options": "nosniff",
            "X-Artifact-SHA256": artifact.sha256_digest,
        },
    )
