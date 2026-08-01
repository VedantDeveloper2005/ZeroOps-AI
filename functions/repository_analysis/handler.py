"""Repository-analysis queue handler.

The deterministic scanner artifact is the factual source of truth. The model
may interpret and prioritize that evidence but cannot invent executable facts
or mutate an infrastructure plan.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from zeroops_functions.ai_contracts import (
    RepositoryAnalysisRequest,
    RepositoryAssessment,
)
from zeroops_functions.blob_store import BlobArtifactStore
from zeroops_functions.contracts import (
    EventArtifactV1,
    RepositoryAnalysisJobV1,
    WorkflowEventV1,
    canonical_artifact_blob_name,
)
from zeroops_functions.identity import workload_credential
from zeroops_functions.model_client import (
    ModelRoutesExhaustedError,
    ModelUnavailableError,
    StructuredModelClient,
    generate_with_fallback,
)
from zeroops_functions.publisher import ServiceBusPublisher
from zeroops_functions.security import canonical_json_bytes, redact, sha256_bytes


@dataclass(frozen=True)
class RepositoryHandlerDependencies:
    store: BlobArtifactStore
    publisher: ServiceBusPublisher
    model_client: StructuredModelClient | None
    workflow_events_queue: str
    instructions: str
    fallback_model_client: StructuredModelClient | None = None


def _evidence_ids(request: RepositoryAnalysisRequest) -> set[str]:
    return {
        *(fact.id for fact in request.source_facts),
        *(excerpt.id for excerpt in request.safe_files),
    }


def _validate_evidence(output: RepositoryAssessment, allowed: set[str]) -> None:
    referenced = {
        reference
        for recommendation in output.recommendations
        for reference in recommendation.evidence_refs
    } | {
        reference
        for optimization in output.cost_optimizations
        for reference in optimization.evidence_refs
    }
    if not allowed and referenced:
        raise ValueError("Model referenced evidence when scanner provided none")
    unknown = referenced - allowed
    if unknown:
        raise ValueError("Model referenced evidence absent from scanner facts")


def _event_id(job: RepositoryAnalysisJobV1, suffix: str) -> str:
    return sha256_bytes(f"{job.job_id}:{job.attempt}:{suffix}".encode("utf-8"))


def dependencies_from_environment() -> RepositoryHandlerDependencies:
    credential = workload_credential()
    account_url = os.environ["ARTIFACT_STORAGE_ACCOUNT_URL"].rstrip("/")
    namespace = os.environ["SERVICEBUS_FULLY_QUALIFIED_NAMESPACE"]
    prompt_path = Path(
        os.getenv(
            "AI_REPOSITORY_INSTRUCTIONS_PATH",
            Path(__file__).parent / "prompts" / "instructions.md",
        )
    )
    instructions = prompt_path.read_text(encoding="utf-8")
    provider = os.getenv("AI_REPOSITORY_PROVIDER", "nvidia")
    if provider.strip().lower().replace("_", "-") != "nvidia":
        raise ValueError("Repository primary provider must be NVIDIA")
    api_key = os.getenv("AI_REPOSITORY_API_KEY", "")
    model_client: StructuredModelClient | None
    try:
        model_client = StructuredModelClient(
            provider=provider,
            endpoint=os.getenv(
                "AI_REPOSITORY_ENDPOINT",
                "https://integrate.api.nvidia.com/v1",
            ),
            model=os.getenv("AI_REPOSITORY_MODEL", "z-ai/glm-5.2"),
            api_key=api_key,
            workload="repository-analysis",
            prompt_version=os.getenv(
                "AI_REPOSITORY_PROMPT_VERSION",
                "repository-analysis.v1",
            ),
            maximum_input_chars=int(
                os.getenv("AI_REPOSITORY_MAX_INPUT_CHARS", "40000")
            ),
            maximum_output_tokens=int(
                os.getenv("AI_REPOSITORY_MAX_OUTPUT_TOKENS", "1600")
            ),
            api_version=os.getenv("AI_GITHUB_API_VERSION", "2026-03-10"),
        )
    except ModelUnavailableError:
        model_client = None
    fallback_provider = os.getenv("AI_REPOSITORY_FALLBACK_PROVIDER", "groq")
    if fallback_provider.strip().lower().replace("_", "-") != "groq":
        raise ValueError("Repository fallback provider must be Groq")
    try:
        fallback_model_client: StructuredModelClient | None = StructuredModelClient(
            provider=fallback_provider,
            endpoint=os.getenv(
                "AI_REPOSITORY_FALLBACK_ENDPOINT",
                "https://api.groq.com/openai/v1",
            ),
            model=os.getenv(
                "AI_REPOSITORY_FALLBACK_MODEL",
                "openai/gpt-oss-120b",
            ),
            api_key=os.getenv("AI_REPOSITORY_FALLBACK_API_KEY", ""),
            workload="repository-analysis",
            prompt_version=os.getenv(
                "AI_REPOSITORY_FALLBACK_PROMPT_VERSION",
                "repository-analysis.v1",
            ),
            maximum_input_chars=int(
                os.getenv("AI_REPOSITORY_FALLBACK_MAX_INPUT_CHARS", "14000")
            ),
            maximum_output_tokens=int(
                os.getenv("AI_REPOSITORY_FALLBACK_MAX_OUTPUT_TOKENS", "800")
            ),
            timeout_seconds=float(
                os.getenv("AI_REPOSITORY_FALLBACK_TIMEOUT_SECONDS", "30")
            ),
        )
    except ModelUnavailableError:
        fallback_model_client = None
    return RepositoryHandlerDependencies(
        store=BlobArtifactStore(account_url, credential),
        publisher=ServiceBusPublisher(namespace, credential),
        model_client=model_client,
        workflow_events_queue=os.getenv(
            "WORKFLOW_EVENTS_QUEUE_NAME",
            "workflow-events",
        ),
        instructions=instructions,
        fallback_model_client=fallback_model_client,
    )


def handle_repository_analysis(
    raw_message: bytes,
    dependencies: RepositoryHandlerDependencies | None = None,
) -> dict[str, Any]:
    deps = dependencies or dependencies_from_environment()
    job = RepositoryAnalysisJobV1.model_validate_json(raw_message)
    started = WorkflowEventV1(
        event_id=_event_id(job, "started"),
        event_type="repository.analysis.started",
        tenant_id=job.tenant_id,
        project_id=job.project_id,
        run_id=job.run_id,
        correlation_id=job.correlation_id,
        stage="repository-analysis",
        attempt=job.attempt,
        status="started",
        actor_type="function",
        actor_id="repository-analysis",
        safe_metadata={
            "source_commit": job.source_commit,
            "scanner_version": job.scanner_version,
        },
    )
    deps.publisher.send_event(deps.workflow_events_queue, started)

    try:
        request_value = deps.store.download_verified_json(
            job.scanner_facts_artifact,
            maximum_bytes=8 * 1024 * 1024,
        )
        request = RepositoryAnalysisRequest.model_validate(request_value)
        if (
            str(request.tenant_id) != job.tenant_id
            or str(request.project_id) != job.project_id
            or request.commit_sha != job.source_commit
        ):
            raise ValueError(
                "Repository-analysis request identity or source revision does not match the job."
            )
        available_evidence = _evidence_ids(request)
        status = "model_assisted"
        provenance: dict[str, Any]
        try:
            model_output, model_provenance, routing = generate_with_fallback(
                primary=deps.model_client,
                fallback=deps.fallback_model_client,
                system_instructions=deps.instructions,
                input_value=request.model_dump(mode="json"),
                output_model=RepositoryAssessment,
                schema_version="repository-assessment.v1",
                correlation_id=job.correlation_id,
                semantic_validator=lambda value: _validate_evidence(
                    value,
                    available_evidence,
                ),
            )
            provenance = {**asdict(model_provenance), **asdict(routing)}
        except ModelRoutesExhaustedError as error:
            status = "deterministic_only"
            model_output = RepositoryAssessment(
                schema_version="repository-assessment.v1",
                summary=(
                    "Deterministic repository scanning completed. Neither model route "
                    "returned a valid structured result."
                ),
                deployment_risk=(
                    "Deployment risk remains unresolved because model-assisted "
                    "interpretation did not pass strict validation."
                ),
                recommendations=[],
                cost_optimizations=[],
                unresolved_questions=[
                    "Review scanner facts and retry model-assisted analysis if needed."
                ],
                confidence="low",
                limitations=[
                    "Model-assisted analysis was unavailable or blocked by the "
                    "bounded validation and safety policy."
                ],
            )
            provenance = {
                "provider": None,
                "model": None,
                "workload": "repository_analysis",
                "prompt_version": None,
                "schema_version": "repository-assessment.v1",
                "execution_mode": "deterministic_only",
                "correlation_id": job.correlation_id,
                "input_tokens": 0,
                "output_tokens": 0,
                "latency_ms": 0,
                "request_hash": None,
                "repair_attempted": False,
                "cached": False,
                **asdict(error.routing),
            }

        artifact_id = job.output_artifact_id
        result = {
            **model_output.model_dump(mode="json"),
            "analysis_status": status,
            "tenant_id": job.tenant_id,
            "project_id": job.project_id,
            "run_id": job.run_id,
            "source_artifact_id": job.source_artifact.artifact_id,
            "scanner_facts_artifact_id": job.scanner_facts_artifact.artifact_id,
            "source_commit": job.source_commit,
            "scanner_version": job.scanner_version,
            "provenance": provenance,
        }
        result_bytes = canonical_json_bytes(result)
        result_digest = sha256_bytes(result_bytes)
        result_blob_name = canonical_artifact_blob_name(
            artifact_id,
            version=1,
            sha256=result_digest,
        )
        uploaded = deps.store.upload_immutable_bytes(
            container=job.output_container,
            blob_name=result_blob_name,
            body=result_bytes,
            media_type="application/json",
            metadata={
                "artifact-id": artifact_id,
                "tenant-id": job.tenant_id,
                "project-id": job.project_id,
                "run-id": job.run_id,
                "classification": "tenant-analysis",
            },
        )
        if uploaded.sha256 != result_digest or not uploaded.etag:
            raise ValueError("Stored repository analysis failed immutable verification")
        completed = WorkflowEventV1(
            event_id=_event_id(job, "completed"),
            event_type="repository.analysis.completed",
            tenant_id=job.tenant_id,
            project_id=job.project_id,
            run_id=job.run_id,
            correlation_id=job.correlation_id,
            stage="repository-analysis",
            attempt=job.attempt,
            status="degraded" if status == "deterministic_only" else "completed",
            actor_type="function",
            actor_id="repository-analysis",
            artifacts=[
                EventArtifactV1(
                    artifact_id=artifact_id,
                    kind="repository-analysis",
                    sha256=uploaded.sha256,
                    storage_container=job.output_container,
                    storage_path=result_blob_name,
                    blob_version_id=uploaded.version_id,
                    size_bytes=uploaded.size_bytes,
                    content_type="application/json",
                    access_scope="user",
                    sanitization_status="sanitized",
                )
            ],
            safe_metadata=redact(
                {
                    "analysis_status": status,
                    "source_commit": job.source_commit,
                    **provenance,
                    "output_size_bytes": uploaded.size_bytes,
                }
            ),
        )
        deps.publisher.send_event(deps.workflow_events_queue, completed)
        return result
    except Exception as error:
        failed = WorkflowEventV1(
            event_id=_event_id(job, "failed"),
            event_type="repository.analysis.failed",
            tenant_id=job.tenant_id,
            project_id=job.project_id,
            run_id=job.run_id,
            correlation_id=job.correlation_id,
            stage="repository-analysis",
            attempt=job.attempt,
            status="failed",
            actor_type="function",
            actor_id="repository-analysis",
            error_code=type(error).__name__[:96],
            safe_message="Repository analysis failed; the queue retry policy will apply.",
        )
        deps.publisher.send_event(deps.workflow_events_queue, failed)
        raise
