"""Fail-closed Terraform generation and immutable VMSS plan handoff."""

from __future__ import annotations

import io
import os
import stat
import uuid
import zipfile
from dataclasses import asdict, dataclass
from datetime import timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Iterable

from zeroops_functions.ai_contracts import (
    TerraformBundle,
    TerraformGenerationRequest,
)
from zeroops_functions.blob_store import BlobArtifactStore, UploadedArtifact
from zeroops_functions.contracts import (
    EventArtifactV1,
    TerraformGenerationJobV1,
    TerraformInputVariableV1,
    WorkflowEventV1,
    canonical_artifact_blob_name,
)
from zeroops_functions.identity import workload_credential
from zeroops_functions.model_client import (
    ModelRoutesExhaustedError,
    ModelUnavailableError,
    StructuredModelClient,
    generate_with_provenance,
)
from zeroops_functions.publisher import ServiceBusPublisher
from zeroops_functions.security import (
    canonical_json_bytes,
    redact,
    sha256_bytes,
    validate_terraform_bundle,
)


FIXED_ZIP_TIMESTAMP = (1980, 1, 1, 0, 0, 0)
TRUSTED_PROVIDER_LOCK_PATH = Path(__file__).with_name("terraform.lock.hcl")
AUDIT_ARTIFACT_NAME = "terraform-generation-audit.v1"
INPUT_VARIABLES_FILE = "zeroops.auto.tfvars.json"


@dataclass(frozen=True)
class TerraformHandlerDependencies:
    store: BlobArtifactStore
    publisher: ServiceBusPublisher
    model_client: StructuredModelClient | None
    workflow_events_queue: str
    terraform_plan_queue: str
    instructions: str


def _event_id(job: TerraformGenerationJobV1, suffix: str) -> str:
    return sha256_bytes(f"{job.job_id}:{job.attempt}:{suffix}".encode("utf-8"))


def _normalized_text_bytes(value: str) -> bytes:
    normalized = value.replace("\r\n", "\n").replace("\r", "\n").rstrip("\n")
    return (normalized + "\n").encode("utf-8")


def build_deterministic_terraform_zip(
    bundle: TerraformBundle,
    *,
    trusted_provider_lock: str | None = None,
    input_variables_bytes: bytes | None = None,
) -> bytes:
    """Render validated root Terraform files plus the application-owned lock."""

    if bundle.status != "generated":
        raise ValueError("Only generated Terraform can be rendered for execution")
    lock_text = (
        trusted_provider_lock
        if trusted_provider_lock is not None
        else TRUSTED_PROVIDER_LOCK_PATH.read_text(encoding="utf-8")
    )
    lock_bytes = _normalized_text_bytes(lock_text)
    if (
        b'registry.terraform.io/hashicorp/azurerm' not in lock_bytes
        or b'version     = "4.81.0"' not in lock_bytes
    ):
        raise ValueError("Trusted AzureRM provider lock is missing its approved pin")

    members = {
        item.path: _normalized_text_bytes(item.content)
        for item in bundle.files
    }
    if ".terraform.lock.hcl" in members:
        raise ValueError("Model output cannot provide the trusted provider lock")
    members[".terraform.lock.hcl"] = lock_bytes
    if input_variables_bytes is not None:
        if INPUT_VARIABLES_FILE in members:
            raise ValueError("Model output cannot provide application-owned input values")
        members[INPUT_VARIABLES_FILE] = input_variables_bytes

    output = io.BytesIO()
    # ZIP_STORED avoids platform/zlib-dependent output while these small,
    # bounded source bundles remain well below the executor size limit.
    with zipfile.ZipFile(output, mode="w", compression=zipfile.ZIP_STORED) as archive:
        for name in sorted(members):
            info = zipfile.ZipInfo(name, date_time=FIXED_ZIP_TIMESTAMP)
            info.create_system = 3
            info.compress_type = zipfile.ZIP_STORED
            info.external_attr = (stat.S_IFREG | 0o600) << 16
            archive.writestr(info, members[name])
    return output.getvalue()


def _normalized_variable_type(value: str) -> str:
    return "".join(value.split()).lower()


def _render_approved_bundle(request: TerraformGenerationRequest) -> TerraformBundle:
    """Render the only production-supported architecture without executable AI output."""

    expected_resource_types = {
        "azurerm_linux_web_app",
        "azurerm_role_assignment",
    }
    component = request.components[0] if len(request.components) == 1 else None
    properties = component.properties if component is not None else {}
    supported = (
        component is not None
        and component.id == "application"
        and component.service == "Azure App Service"
        and set(request.allowed_resource_types) == expected_resource_types
        and properties.get("create_resource_group") is False
        and properties.get("public_network_access") is True
        and properties.get("managed_identity") == "SystemAssigned"
        and properties.get("container_registry_role") == "AcrPull"
        and properties.get("container_registry_scope") == "configured-registry-only"
    )
    if not supported:
        return TerraformBundle.model_validate(
            {
                "schema_version": "terraform-bundle.v1",
                "status": "blocked",
                "plan_revision": request.plan_revision,
                "plan_sha256": request.plan_sha256,
                "files": [],
                "variables": [],
                "resources": [],
                "outputs": [],
                "assumptions": [],
                "warnings": [],
                "cost_optimizations": [],
                "validation_requirements": [],
                "blocked_reasons": [
                    "The approved architecture is outside the deterministic Azure App Service renderer."
                ],
            }
        )

    files = [
        {
            "path": "versions.tf",
            "content": (
                "terraform {\n"
                '  required_version = "= 1.15.8"\n\n'
                "  required_providers {\n"
                "    azurerm = {\n"
                '      source  = "hashicorp/azurerm"\n'
                '      version = "= 4.81.0"\n'
                "    }\n"
                "  }\n\n"
                '  backend "azurerm" {}\n'
                "}\n"
            ),
        },
        {
            "path": "providers.tf",
            "content": 'provider "azurerm" {\n  features {}\n}\n',
        },
        {
            "path": "variables.tf",
            "content": (
                'variable "application_name" {\n'
                "  type        = string\n"
                '  description = "Deterministic Azure Linux Web App name."\n'
                "}\n\n"
                'variable "app_service_plan_id" {\n'
                "  type        = string\n"
                '  description = "Verified existing Linux App Service plan resource ID."\n'
                "}\n\n"
                'variable "container_registry_id" {\n'
                "  type        = string\n"
                '  description = "Verified existing Azure Container Registry resource ID."\n'
                "}\n\n"
                'variable "location" {\n'
                "  type        = string\n"
                '  description = "Approved Azure region."\n'
                "}\n\n"
                'variable "resource_group_name" {\n'
                "  type        = string\n"
                '  description = "Verified existing resource group name."\n'
                "}\n"
            ),
        },
        {
            "path": "main.tf",
            "content": (
                'resource "azurerm_linux_web_app" "application" {\n'
                "  name                          = var.application_name\n"
                "  resource_group_name           = var.resource_group_name\n"
                "  location                      = var.location\n"
                "  service_plan_id               = var.app_service_plan_id\n"
                "  https_only                    = true\n"
                "  public_network_access_enabled = true\n"
                "  client_affinity_enabled       = false\n\n"
                "  identity {\n"
                '    type = "SystemAssigned"\n'
                "  }\n\n"
                "  site_config {\n"
                '    ftps_state          = "Disabled"\n'
                "    http2_enabled       = true\n"
                '    minimum_tls_version = "1.2"\n'
                "  }\n\n"
                "  tags = {\n"
                '    "managed-by"        = "ZeroOps"\n'
                '    "zeroops-component" = "application"\n'
                "  }\n"
                "}\n\n"
                'resource "azurerm_role_assignment" "application_acr_pull" {\n'
                "  scope                            = var.container_registry_id\n"
                '  role_definition_name             = "AcrPull"\n'
                "  principal_id                     = azurerm_linux_web_app.application.identity[0].principal_id\n"
                "  skip_service_principal_aad_check = true\n"
                "}\n"
            ),
        },
        {
            "path": "outputs.tf",
            "content": (
                'output "application_default_hostname" {\n'
                '  description = "Azure-reported default hostname for the application."\n'
                "  value       = azurerm_linux_web_app.application.default_hostname\n"
                "}\n\n"
                'output "application_principal_id" {\n'
                '  description = "System-assigned identity principal used for ACR pull."\n'
                "  value       = azurerm_linux_web_app.application.identity[0].principal_id\n"
                "}\n"
            ),
        },
    ]
    variables = [
        {
            "name": name,
            "type": "string",
            "description": description,
            "sensitive": False,
            "default": None,
        }
        for name, description in (
            ("application_name", "Deterministic Azure Linux Web App name."),
            ("app_service_plan_id", "Verified existing Linux App Service plan resource ID."),
            ("container_registry_id", "Verified existing Azure Container Registry resource ID."),
            ("location", "Approved Azure region."),
            ("resource_group_name", "Verified existing resource group name."),
        )
    ]
    return TerraformBundle.model_validate(
        {
            "schema_version": "terraform-bundle.v1",
            "status": "generated",
            "plan_revision": request.plan_revision,
            "plan_sha256": request.plan_sha256,
            "files": files,
            "variables": variables,
            "resources": [
                {
                    "address": "azurerm_linux_web_app.application",
                    "resource_type": "azurerm_linux_web_app",
                    "component_id": "application",
                    "rationale": "Creates the approved application on the verified existing Linux plan.",
                    "cost_driver": False,
                },
                {
                    "address": "azurerm_role_assignment.application_acr_pull",
                    "resource_type": "azurerm_role_assignment",
                    "component_id": "application",
                    "rationale": "Grants only AcrPull to the application identity on the verified registry.",
                    "cost_driver": False,
                },
            ],
            "outputs": [
                {
                    "name": "application_default_hostname",
                    "description": "Azure-reported default hostname for the application.",
                    "sensitive": False,
                },
                {
                    "name": "application_principal_id",
                    "description": "System-assigned identity principal used for ACR pull.",
                    "sensitive": False,
                },
            ],
            "assumptions": [
                "The resource group, Linux App Service plan, and container registry were verified before approval."
            ],
            "warnings": [
                "This infrastructure plan does not publish an application image or configure runtime settings."
            ],
            "cost_optimizations": [],
            "validation_requirements": [
                "Run terraform fmt -check.",
                "Run terraform init with the protected AzureRM backend.",
                "Run terraform validate.",
                "Run TFLint.",
                "Run Checkov.",
                "Run terraform plan and enforce the approved scope and resource allowlist.",
                "Verify immutable pricing and budget evidence for the exact saved plan.",
                "Require human approval of the exact saved plan before apply.",
            ],
            "blocked_reasons": [],
        }
    )


def _deterministic_provenance(
    request: TerraformGenerationRequest,
    *,
    correlation_id: str,
) -> dict[str, Any]:
    return {
        "workload": "terraform-generation",
        "provider": "zeroops",
        "model": "deterministic-app-service-renderer.v1",
        "prompt_version": "none",
        "schema_version": "terraform-bundle.v1",
        "execution_mode": "deterministic_only",
        "correlation_id": correlation_id,
        "request_hash": sha256_bytes(
            canonical_json_bytes(request.model_dump(mode="json"))
        ),
        "input_tokens": 0,
        "output_tokens": 0,
        "latency_ms": 0,
        "repair_attempted": False,
        "cached": False,
        "selected_route": "none",
        "fallback_attempted": False,
        "primary_failure_code": None,
    }


def _render_input_variables(
    bundle: TerraformBundle,
    input_variables: Iterable[TerraformInputVariableV1],
) -> tuple[bytes, list[dict[str, str]]]:
    """Validate approved non-secret inputs against generated declarations."""

    supplied_variables = list(input_variables)
    declared = {item.name: item for item in bundle.variables}
    provided = {item.name: item for item in supplied_variables}
    if len(provided) != len(supplied_variables):
        raise ValueError("Terraform input variable names must be unique")

    sensitive = sorted(item.name for item in bundle.variables if item.sensitive)
    if sensitive:
        raise ValueError(
            "Generated Terraform requires sensitive inputs, but no secret execution channel exists"
        )

    extra = sorted(set(provided) - set(declared))
    if extra:
        raise ValueError("Approved Terraform inputs contain undeclared variables")
    missing = sorted(
        item.name
        for item in bundle.variables
        if item.default is None and item.name not in provided
    )
    if missing:
        raise ValueError("Generated Terraform has required variables without approved values")

    definitions: list[dict[str, str]] = []
    values: dict[str, Any] = {}
    for name in sorted(provided):
        supplied = provided[name]
        expected_type = _normalized_variable_type(declared[name].type)
        if expected_type != supplied.type:
            raise ValueError("Approved Terraform input type differs from generated metadata")
        definitions.append({"name": supplied.name, "type": supplied.type})
        values[supplied.name] = supplied.value

    body = canonical_json_bytes(values) + b"\n"
    if len(body) > 64 * 1024:
        raise ValueError("Canonical Terraform input values exceed 64 KiB")
    return body, definitions


def _microunits(value: float | None) -> int | None:
    if value is None:
        return None
    return int(
        (Decimal(str(value)) * Decimal(1_000_000)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def _execution_guardrails(
    *,
    job: TerraformGenerationJobV1,
    request: TerraformGenerationRequest,
) -> dict[str, Any]:
    allowed_resource_types = sorted(request.allowed_resource_types)
    scope_material = {
        "target_subscription_id": job.target_subscription_id,
        "target_tenant_id": job.target_tenant_id,
        "target_resource_group": job.target_resource_group,
        "allowed_resource_types": allowed_resource_types,
        "component_ids": sorted(component.id for component in request.components),
    }
    policy_material = {
        "module_catalog_version": request.module_catalog_version,
        "policy_version": request.policy_version,
        "constraints": request.constraints,
        "maximum_resource_changes": job.maximum_resource_changes,
        "maximum_delete_count": job.maximum_delete_count,
        "maximum_replace_count": job.maximum_replace_count,
    }
    pricing = request.pricing
    return {
        "target_resource_group": job.target_resource_group,
        "allowed_resource_types": allowed_resource_types,
        "maximum_resource_changes": job.maximum_resource_changes,
        "maximum_delete_count": job.maximum_delete_count,
        "maximum_replace_count": job.maximum_replace_count,
        "scope_digest": sha256_bytes(canonical_json_bytes(scope_material)),
        "policy_digest": sha256_bytes(canonical_json_bytes(policy_material)),
        "monthly_budget_microunits": (
            _microunits(pricing.monthly_budget) if pricing is not None else None
        ),
        "budget_currency": pricing.currency if pricing is not None else None,
    }


def _artifact_uri(
    store: BlobArtifactStore,
    *,
    container: str,
    blob_name: str,
) -> str:
    return f"{store.account_url.rstrip('/')}/{container}/{blob_name}"


def _require_upload_etag(uploaded: UploadedArtifact) -> str:
    if not uploaded.etag:
        raise ValueError("Immutable artifact upload did not return a storage ETag")
    return uploaded.etag


def _requested_at(job: TerraformGenerationJobV1) -> str:
    return (
        job.enqueued_at.astimezone(timezone.utc)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def _execution_envelope(
    *,
    job: TerraformGenerationJobV1,
    store: BlobArtifactStore,
    bundle_blob_name: str,
    uploaded_bundle: UploadedArtifact,
    input_variables_bytes: bytes,
    input_variable_definitions: list[dict[str, str]],
    guardrails: dict[str, Any],
) -> dict[str, Any]:
    plan_job_id = str(uuid.uuid5(uuid.UUID(job.job_id), "terraform-plan.v1"))
    value: dict[str, Any] = {
        "schema_version": "1.0",
        "operation": "plan",
        "job_id": plan_job_id,
        "tenant_id": job.tenant_id,
        "project_id": job.project_id,
        "user_id": job.user_id,
        "workflow_id": job.run_id,
        "revision": job.approved_plan_revision,
        "bundle": {
            "uri": _artifact_uri(
                store,
                container=job.output_container,
                blob_name=bundle_blob_name,
            ),
            "etag": _require_upload_etag(uploaded_bundle),
            "sha256": uploaded_bundle.sha256,
            "size_bytes": uploaded_bundle.size_bytes,
        },
        "input_variables": {
            "file_name": INPUT_VARIABLES_FILE,
            "sha256": sha256_bytes(input_variables_bytes),
            "definitions": input_variable_definitions,
        },
        "guardrails": guardrails,
        "state_key": (
            f"tenants/{job.tenant_id}/workspaces/{job.run_id}/terraform.tfstate"
        ),
        "target_subscription_id": job.target_subscription_id,
        "target_tenant_id": job.target_tenant_id,
        "terraform_version": job.terraform_version,
        "requested_at": _requested_at(job),
    }
    value["job_digest"] = sha256_bytes(canonical_json_bytes(value))
    return value


def _upload_audit(
    *,
    job: TerraformGenerationJobV1,
    deps: TerraformHandlerDependencies,
    audit_value: dict[str, Any],
) -> tuple[str, str, UploadedArtifact]:
    audit_artifact_id = str(
        uuid.uuid5(uuid.UUID(job.output_artifact_id), AUDIT_ARTIFACT_NAME)
    )
    body = canonical_json_bytes(audit_value)
    blob_name = canonical_artifact_blob_name(
        audit_artifact_id,
        version=1,
        sha256=sha256_bytes(body),
    )
    uploaded = deps.store.upload_immutable_bytes(
        container=job.output_container,
        blob_name=blob_name,
        body=body,
        media_type="application/json",
        metadata={
            "artifact-id": audit_artifact_id,
            "tenant-id": job.tenant_id,
            "project-id": job.project_id,
            "run-id": job.run_id,
            "classification": "tenant-terraform",
            "artifact-purpose": "generation-audit",
            "approved-plan-digest": job.approved_plan_digest,
        },
    )
    if uploaded.sha256 != sha256_bytes(body):
        raise ValueError("Stored Terraform audit digest differs from its canonical bytes")
    _require_upload_etag(uploaded)
    return audit_artifact_id, blob_name, uploaded


def dependencies_from_environment() -> TerraformHandlerDependencies:
    credential = workload_credential()
    account_url = os.environ["ARTIFACT_STORAGE_ACCOUNT_URL"].rstrip("/")
    namespace = os.environ["SERVICEBUS_FULLY_QUALIFIED_NAMESPACE"]
    prompt_path = Path(
        os.getenv(
            "AI_TERRAFORM_INSTRUCTIONS_PATH",
            Path(__file__).parent / "prompts" / "instructions.md",
        )
    )
    primary_provider = os.getenv("AI_TERRAFORM_PROVIDER", "azure-openai")
    if primary_provider.strip().lower().replace("_", "-") not in {
        "azure-openai",
        "azure-foundry",
        "foundry-openai",
        "microsoft-foundry-openai",
    }:
        raise ValueError("Terraform primary provider must be Microsoft Foundry OpenAI")
    try:
        model_client: StructuredModelClient | None = StructuredModelClient(
            provider=primary_provider,
            credential=credential,
            agent_name=os.getenv("FOUNDRY_AGENT_NAME", "zeroops-architecture-advisor"),
            agent_version=os.getenv("FOUNDRY_AGENT_VERSION", "3"),
            timeout_seconds=120.0,
            endpoint=os.getenv(
                "AI_TERRAFORM_ENDPOINT",
                "",
            ),
            model=os.getenv("AI_TERRAFORM_MODEL", ""),
            api_key=os.getenv("AI_TERRAFORM_API_KEY", ""),
            workload="terraform-generation",
            prompt_version=os.getenv(
                "AI_TERRAFORM_PROMPT_VERSION",
                "terraform-generation.v1",
            ),
            maximum_input_chars=int(
                os.getenv("AI_TERRAFORM_MAX_INPUT_CHARS", "40000")
            ),
            maximum_output_tokens=int(
                os.getenv("AI_TERRAFORM_MAX_OUTPUT_TOKENS", "4000")
            ),
        )
    except ModelUnavailableError:
        model_client = None
    return TerraformHandlerDependencies(
        store=BlobArtifactStore(account_url, credential),
        publisher=ServiceBusPublisher(namespace, credential),
        model_client=model_client,
        workflow_events_queue=os.getenv(
            "WORKFLOW_EVENTS_QUEUE_NAME",
            "workflow-events",
        ),
        terraform_plan_queue=os.getenv("TERRAFORM_PLAN_QUEUE_NAME", "terraform-plan"),
        instructions=prompt_path.read_text(encoding="utf-8"),
    )


def handle_terraform_generation(
    raw_message: bytes,
    dependencies: TerraformHandlerDependencies | None = None,
) -> dict[str, Any]:
    deps = dependencies or dependencies_from_environment()
    job = TerraformGenerationJobV1.model_validate_json(raw_message)
    deps.publisher.send_event(
        deps.workflow_events_queue,
        WorkflowEventV1(
            event_id=_event_id(job, "started"),
            event_type="terraform.generation.started",
            tenant_id=job.tenant_id,
            project_id=job.project_id,
            run_id=job.run_id,
            correlation_id=job.correlation_id,
            stage="terraform-generation",
            attempt=job.attempt,
            status="started",
            actor_type="function",
            actor_id="terraform-generation",
            safe_metadata={
                "approved_plan_id": job.approved_plan_id,
                "approved_plan_revision": job.approved_plan_revision,
                "approved_plan_digest": job.approved_plan_digest,
                "target_environment": job.target_environment,
                "terraform_version": job.terraform_version,
            },
        ),
    )
    try:
        request_value = deps.store.download_verified_json(
            job.approved_plan_artifact,
            maximum_bytes=8 * 1024 * 1024,
        )
        request = TerraformGenerationRequest.model_validate(request_value)
        if (
            str(request.tenant_id) != job.tenant_id
            or str(request.project_id) != job.project_id
            or str(request.plan_id) != job.approved_plan_id
            or request.plan_revision != job.approved_plan_revision
            or request.plan_sha256 != job.approved_plan_digest
        ):
            raise ValueError(
                "Terraform request identity, revision, or approved-plan digest mismatch."
            )
        if getattr(deps.model_client, "provider", None) == "azure-foundry":
            bundle, provenance, routing = generate_with_provenance(
                primary=deps.model_client,
                system_instructions=deps.instructions,
                input_value=request.model_dump(mode="json"),
                output_model=TerraformBundle,
                schema_version="terraform-bundle.v1",
                correlation_id=job.correlation_id,
                semantic_validator=lambda value: validate_terraform_bundle(value, request),
            )
            provenance_value = {**asdict(provenance), "routing": asdict(routing)}
        else:
            bundle = _render_approved_bundle(request)
            provenance_value = _deterministic_provenance(
                request,
                correlation_id=job.correlation_id,
            )
        validate_terraform_bundle(bundle, request)
        ordered_files = sorted(bundle.files, key=lambda item: item.path)
        file_manifest = [
            {
                "path": item.path,
                "sha256": sha256_bytes(_normalized_text_bytes(item.content)),
                "size_bytes": len(_normalized_text_bytes(item.content)),
            }
            for item in ordered_files
        ]
        audit_value: dict[str, Any] = {
            **bundle.model_dump(mode="json"),
            "tenant_id": job.tenant_id,
            "project_id": job.project_id,
            "user_id": job.user_id,
            "run_id": job.run_id,
            "approved_plan_id": job.approved_plan_id,
            "approved_plan_revision": job.approved_plan_revision,
            "approved_plan_digest": job.approved_plan_digest,
            "target_environment": job.target_environment,
            "target_subscription_id": job.target_subscription_id,
            "target_tenant_id": job.target_tenant_id,
            "terraform_version": job.terraform_version,
            "file_manifest": file_manifest,
            "bundle_content_digest": sha256_bytes(
                canonical_json_bytes(
                    {
                        "files": [
                            {
                                "path": item.path,
                                "content_sha256": sha256_bytes(
                                    _normalized_text_bytes(item.content)
                                ),
                            }
                            for item in ordered_files
                        ],
                        "approved_plan_digest": job.approved_plan_digest,
                    }
                )
            ),
            "provenance": provenance_value,
            "validation_status": "not_run",
            "plan_status": "not_run",
            "apply_status": "not_run",
        }

        if bundle.status == "blocked":
            audit_artifact_id, audit_blob_name, uploaded_audit = _upload_audit(
                job=job,
                deps=deps,
                audit_value=audit_value,
            )
            deps.publisher.send_event(
                deps.workflow_events_queue,
                WorkflowEventV1(
                    event_id=_event_id(job, "blocked"),
                    event_type="terraform.generation.blocked",
                    tenant_id=job.tenant_id,
                    project_id=job.project_id,
                    run_id=job.run_id,
                    correlation_id=job.correlation_id,
                    stage="terraform-generation",
                    attempt=job.attempt,
                    status="failed",
                    actor_type="function",
                    actor_id="terraform-generation",
                    artifacts=[
                        EventArtifactV1(
                            artifact_id=audit_artifact_id,
                            kind="terraform-generation-audit",
                            sha256=uploaded_audit.sha256,
                            storage_container=job.output_container,
                            storage_path=audit_blob_name,
                            blob_version_id=uploaded_audit.version_id,
                            size_bytes=uploaded_audit.size_bytes,
                            content_type="application/json",
                            access_scope="user",
                            sanitization_status="sanitized",
                        )
                    ],
                    safe_metadata={
                        "approved_plan_digest": job.approved_plan_digest,
                        "blocked_reason_count": len(bundle.blocked_reasons),
                        "validation_status": "not_run",
                        "plan_status": "not_run",
                        "apply_status": "not_run",
                    },
                    safe_message=(
                        "Terraform generation was blocked; no plan job was enqueued."
                    ),
                ),
            )
            return audit_value

        input_variables_bytes, input_variable_definitions = _render_input_variables(
            bundle,
            job.input_variables,
        )
        guardrails = _execution_guardrails(job=job, request=request)
        bundle_bytes = build_deterministic_terraform_zip(
            bundle,
            input_variables_bytes=input_variables_bytes,
        )
        bundle_sha256 = sha256_bytes(bundle_bytes)
        bundle_blob_name = canonical_artifact_blob_name(
            job.output_artifact_id,
            version=1,
            sha256=bundle_sha256,
        )
        uploaded_bundle = deps.store.upload_immutable_bytes(
            container=job.output_container,
            blob_name=bundle_blob_name,
            body=bundle_bytes,
            media_type="application/zip",
            metadata={
                "artifact-id": job.output_artifact_id,
                "tenant-id": job.tenant_id,
                "project-id": job.project_id,
                "run-id": job.run_id,
                "classification": "tenant-terraform",
                "artifact-purpose": "executor-bundle",
                "approved-plan-digest": job.approved_plan_digest,
                "terraform-version": job.terraform_version,
            },
        )
        if (
            uploaded_bundle.sha256 != bundle_sha256
            or uploaded_bundle.size_bytes != len(bundle_bytes)
        ):
            raise ValueError("Stored Terraform bundle differs from deterministic ZIP")
        _require_upload_etag(uploaded_bundle)

        envelope = _execution_envelope(
            job=job,
            store=deps.store,
            bundle_blob_name=bundle_blob_name,
            uploaded_bundle=uploaded_bundle,
            input_variables_bytes=input_variables_bytes,
            input_variable_definitions=input_variable_definitions,
            guardrails=guardrails,
        )
        audit_value["executor_bundle"] = {
            "artifact_id": job.output_artifact_id,
            "sha256": uploaded_bundle.sha256,
            "size_bytes": uploaded_bundle.size_bytes,
            "media_type": "application/zip",
            "terraform_version": job.terraform_version,
            "plan_job_id": envelope["job_id"],
            "plan_job_digest": envelope["job_digest"],
            "input_variables_sha256": envelope["input_variables"]["sha256"],
            "scope_digest": guardrails["scope_digest"],
            "policy_digest": guardrails["policy_digest"],
        }
        audit_artifact_id, audit_blob_name, uploaded_audit = _upload_audit(
            job=job,
            deps=deps,
            audit_value=audit_value,
        )

        deps.publisher.send_json(
            deps.terraform_plan_queue,
            envelope,
            message_id=envelope["job_digest"],
            correlation_id=job.correlation_id,
            subject="terraform.plan.requested",
            session_id=job.run_id,
        )
        deps.publisher.send_event(
            deps.workflow_events_queue,
            WorkflowEventV1(
                event_id=_event_id(job, "completed"),
                event_type="terraform.generation.completed",
                tenant_id=job.tenant_id,
                project_id=job.project_id,
                run_id=job.run_id,
                correlation_id=job.correlation_id,
                stage="terraform-generation",
                attempt=job.attempt,
                status="completed",
                actor_type="function",
                actor_id="terraform-generation",
                artifacts=[
                    EventArtifactV1(
                        artifact_id=audit_artifact_id,
                        kind="terraform-generation-audit",
                        sha256=uploaded_audit.sha256,
                        storage_container=job.output_container,
                        storage_path=audit_blob_name,
                        blob_version_id=uploaded_audit.version_id,
                        size_bytes=uploaded_audit.size_bytes,
                        content_type="application/json",
                        access_scope="user",
                        sanitization_status="sanitized",
                    ),
                    EventArtifactV1(
                        artifact_id=job.output_artifact_id,
                        kind="terraform-bundle",
                        sha256=uploaded_bundle.sha256,
                        storage_container=job.output_container,
                        storage_path=bundle_blob_name,
                        blob_version_id=uploaded_bundle.version_id,
                        size_bytes=uploaded_bundle.size_bytes,
                        content_type="application/zip",
                        access_scope="user",
                        sanitization_status="sanitized",
                    ),
                ],
                safe_metadata=redact(
                    {
                        **provenance_value,
                        "approved_plan_digest": job.approved_plan_digest,
                        "target_environment": job.target_environment,
                        "terraform_version": job.terraform_version,
                        "file_count": len(bundle.files),
                        "bundle_size_bytes": uploaded_bundle.size_bytes,
                        "plan_job_digest": envelope["job_digest"],
                        "validation_status": "not_run",
                        "plan_status": "not_run",
                        "apply_status": "not_run",
                    }
                ),
            ),
        )
        return audit_value
    except Exception as error:
        failure_metadata = (
            asdict(error.routing)
            if isinstance(error, ModelRoutesExhaustedError)
            else {}
        )
        deps.publisher.send_event(
            deps.workflow_events_queue,
            WorkflowEventV1(
                event_id=_event_id(job, "failed"),
                event_type="terraform.generation.failed",
                tenant_id=job.tenant_id,
                project_id=job.project_id,
                run_id=job.run_id,
                correlation_id=job.correlation_id,
                stage="terraform-generation",
                attempt=job.attempt,
                status="failed",
                actor_type="function",
                actor_id="terraform-generation",
                error_code=type(error).__name__[:96],
                safe_metadata=redact(failure_metadata),
                safe_message=(
                    "Terraform generation failed closed; no plan job was enqueued."
                ),
            ),
        )
        raise
