"""Backend control-plane orchestration for Terraform generation and apply."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Any, Mapping
import uuid

from fastapi import HTTPException, status
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

try:
    from backend import config, models
    from backend.contracts.ai import ApprovedComponent, TerraformGenerationRequest, VerifiedPricingContext
    from backend.contracts.workflow import (
        ApplyApprovalV1,
        ArtifactReferenceV1,
        BundleReferenceV1,
        ExecutionGuardrailsV1,
        InputVariablesReferenceV1,
        SavedPlanReferenceV1,
        TerraformApplyEnvelopeV1,
        TerraformGenerationJobV1,
        TerraformInputVariableV1,
        VerifiedCostEstimateV1,
        canonical_digest,
        canonical_json_bytes,
    )
    from backend.services import artifacts, deployment_targets, history, workflow_outbox
except ImportError:  # pragma: no cover - backend-directory execution
    import config, models
    from contracts.ai import ApprovedComponent, TerraformGenerationRequest, VerifiedPricingContext
    from contracts.workflow import (
        ApplyApprovalV1,
        ArtifactReferenceV1,
        BundleReferenceV1,
        ExecutionGuardrailsV1,
        InputVariablesReferenceV1,
        SavedPlanReferenceV1,
        TerraformApplyEnvelopeV1,
        TerraformGenerationJobV1,
        TerraformInputVariableV1,
        VerifiedCostEstimateV1,
        canonical_digest,
        canonical_json_bytes,
    )
    from services import artifacts, deployment_targets, history, workflow_outbox


MODULE_CATALOG_VERSION = "zeroops-modules.v1"
POLICY_VERSION = "zeroops-terraform-policy.v1"
TERRAFORM_VERSION = "1.15.8"
_RESOURCE_TYPES = {
    "Azure App Service": (
        "azurerm_resource_group",
        "azurerm_linux_web_app",
        "azurerm_role_assignment",
    ),
}
_ZERO_INCREMENTAL_FIXED_COST_RESOURCE_TYPES = frozenset(
    {"azurerm_resource_group", "azurerm_linux_web_app", "azurerm_role_assignment"}
)
_ACR_LOGIN_SERVER = re.compile(r"^(?P<name>[a-z0-9]{5,50})\.azurecr\.io$")
_PLAN_ACTIONS = ("create", "update", "delete", "replace", "read", "no_op")
_HEX_64 = re.compile(r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class QueuedTerraformGeneration:
    operation_run_id: uuid.UUID
    outbox_message_id: uuid.UUID
    plan_digest: str
    artifact_id: uuid.UUID
    idempotent: bool


@dataclass(frozen=True)
class ConsumedTerraformApproval:
    operation_run_id: uuid.UUID
    approval_id: uuid.UUID
    apply_job_id: uuid.UUID
    outbox_message_id: uuid.UUID
    idempotent: bool


@dataclass(frozen=True)
class VerifiedTerraformCost:
    operation_run_id: uuid.UUID
    artifact_id: uuid.UUID
    artifact_sha256: str
    currency: str
    monthly_cost_microunits: int
    captured_at: datetime
    idempotent: bool


@dataclass(frozen=True)
class CompletedTerraformApply:
    operation_run_id: uuid.UUID
    approval_id: uuid.UUID
    apply_job_id: uuid.UUID
    plan_digest: str
    plan_job_digest: str
    plan_sha256: str
    bundle_sha256: str
    target_fingerprint: str
    completion_event_id: str
    completed_at: datetime

    def deployment_metadata(self) -> dict[str, Any]:
        return {
            "schema_version": "terraform-apply-proof.v1",
            "operation_run_id": str(self.operation_run_id),
            "approval_id": str(self.approval_id),
            "apply_job_id": str(self.apply_job_id),
            "approved_plan_digest": self.plan_digest,
            "plan_job_digest": self.plan_job_digest,
            "plan_sha256": self.plan_sha256,
            "bundle_sha256": self.bundle_sha256,
            "target_fingerprint": self.target_fingerprint,
            "completion_event_id": self.completion_event_id,
            "completed_at": self.completed_at.isoformat(),
        }


def approved_plan_digest(plan: models.InfrastructurePlan) -> str:
    """Bind the exact approved architecture revision, including cost evidence."""

    return canonical_digest(
        {
            "id": str(plan.id),
            "project_id": str(plan.project_id),
            "provider": plan.provider,
            "region": plan.region,
            "status": plan.status,
            "revision": plan.revision,
            "plan": plan.plan_data or {},
            "cost_estimate": plan.cost_estimate,
        }
    )


async def find_completed_apply_for_plan(
    db: AsyncSession,
    *,
    tenant: models.Tenant,
    user: models.User,
    project: models.Project,
    plan: models.InfrastructurePlan,
    azure_connection: models.UserAzureConnection,
) -> CompletedTerraformApply | None:
    """Return proof only when the current plan and target were applied exactly."""

    if (
        project.user_id != user.id
        or plan.project_id != project.id
        or plan.user_id != user.id
        or plan.status != "approved"
        or azure_connection.user_id != user.id
        or not deployment_targets.has_verified_app_service_target(azure_connection)
    ):
        return None
    current_digest = approved_plan_digest(plan)
    target_fingerprint = str(azure_connection.deployment_target_fingerprint or "")
    result = await db.execute(
        select(
            models.OperationRun,
            models.TerraformPlanResult,
            models.TerraformApplyApproval,
            models.ActivityEvent,
        )
        .join(
            models.TerraformPlanResult,
            models.TerraformPlanResult.operation_run_id == models.OperationRun.id,
        )
        .join(
            models.TerraformApplyApproval,
            models.TerraformApplyApproval.operation_run_id == models.OperationRun.id,
        )
        .join(
            models.ActivityEvent,
            models.ActivityEvent.operation_run_id == models.OperationRun.id,
        )
        .where(
            models.OperationRun.project_id == project.id,
            models.OperationRun.tenant_id == tenant.id,
            models.OperationRun.requested_by_user_id == user.id,
            models.OperationRun.operation_type == "infrastructure_pipeline",
            models.OperationRun.status == "completed",
            models.OperationRun.input_digest == current_digest,
            models.TerraformPlanResult.project_id == project.id,
            models.TerraformPlanResult.tenant_id == tenant.id,
            models.TerraformPlanResult.revision == plan.revision,
            models.TerraformApplyApproval.project_id == project.id,
            models.TerraformApplyApproval.tenant_id == tenant.id,
            models.TerraformApplyApproval.approved_by_user_id == user.id,
            models.TerraformApplyApproval.status == "consumed",
            models.ActivityEvent.project_id == project.id,
            models.ActivityEvent.tenant_id == tenant.id,
            models.ActivityEvent.action == "terraform.apply.completed",
            models.ActivityEvent.actor_type == "vmss",
            models.ActivityEvent.actor_id == "terraform-executor",
        )
        .order_by(models.ActivityEvent.created_at.desc())
        .limit(1)
    )
    row = result.first()
    if row is None:
        return None
    operation_run, plan_result, approval, completion_event = row
    summary = operation_run.summary if isinstance(operation_run.summary, Mapping) else {}
    if (
        summary.get("approved_plan_id") != str(plan.id)
        or summary.get("approved_plan_revision") != plan.revision
        or summary.get("approved_plan_digest") != current_digest
        or summary.get("target_fingerprint") != target_fingerprint
    ):
        return None
    try:
        bundle = BundleReferenceV1.model_validate(plan_result.bundle)
        input_variables = InputVariablesReferenceV1.model_validate(plan_result.input_variables)
        guardrails = ExecutionGuardrailsV1.model_validate(plan_result.guardrails)
        saved_plan = SavedPlanReferenceV1.model_validate(plan_result.saved_plan)
        cost = VerifiedCostEstimateV1.model_validate(plan_result.cost_estimate)
    except (TypeError, ValueError):
        return None
    if (
        approval.plan_job_digest != plan_result.plan_job_digest
        or approval.plan_sha256 != saved_plan.sha256
        or approval.bundle_sha256 != bundle.sha256
        or approval.input_variables_sha256 != input_variables.sha256
        or approval.scope_digest != guardrails.scope_digest
        or approval.policy_digest != guardrails.policy_digest
        or approval.cost_estimate_sha256 != cost.artifact_sha256
        or approval.currency != cost.currency
        or approval.monthly_cost_microunits != cost.monthly_cost_microunits
        or saved_plan.plan_job_digest != plan_result.plan_job_digest
        or saved_plan.bundle_sha256 != bundle.sha256
        or saved_plan.input_variables_sha256 != input_variables.sha256
        or saved_plan.scope_digest != guardrails.scope_digest
        or saved_plan.policy_digest != guardrails.policy_digest
    ):
        return None
    event_data = completion_event.event_data if isinstance(completion_event.event_data, Mapping) else {}
    metadata = event_data.get("metadata") if isinstance(event_data.get("metadata"), Mapping) else {}
    if (
        event_data.get("status") != "completed"
        or event_data.get("stage") != "terraform-apply"
        or metadata.get("operation") != "apply"
        or metadata.get("job_id") != str(approval.apply_job_id)
        or metadata.get("approval_id") != str(approval.id)
        or metadata.get("plan_sha256") != approval.plan_sha256
        or metadata.get("bundle_sha256") != approval.bundle_sha256
        or not completion_event.external_event_id
        or not completion_event.event_fingerprint
    ):
        return None
    completed_at = completion_event.created_at
    if completed_at.tzinfo is None:
        completed_at = completed_at.replace(tzinfo=timezone.utc)
    return CompletedTerraformApply(
        operation_run_id=operation_run.id,
        approval_id=approval.id,
        apply_job_id=approval.apply_job_id,
        plan_digest=current_digest,
        plan_job_digest=plan_result.plan_job_digest,
        plan_sha256=approval.plan_sha256,
        bundle_sha256=approval.bundle_sha256,
        target_fingerprint=target_fingerprint,
        completion_event_id=completion_event.external_event_id,
        completed_at=completed_at.astimezone(timezone.utc),
    )


async def require_completed_apply_for_plan(
    db: AsyncSession,
    *,
    tenant: models.Tenant,
    user: models.User,
    project: models.Project,
    plan: models.InfrastructurePlan,
    azure_connection: models.UserAzureConnection,
) -> CompletedTerraformApply:
    proof = await find_completed_apply_for_plan(
        db,
        tenant=tenant,
        user=user,
        project=project,
        plan=plan,
        azure_connection=azure_connection,
    )
    if proof is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Generate the Terraform plan, review its exact changes and verified cost, "
                "approve the saved plan once, and wait for its successful Azure apply before deployment."
            ),
        )
    return proof


def _verified_pricing(plan: models.InfrastructurePlan) -> VerifiedPricingContext | None:
    value = plan.cost_estimate
    if not isinstance(value, Mapping) or value.get("status") != "verified":
        return None
    try:
        return VerifiedPricingContext.model_validate(
            {
                "currency": value["currency"],
                "captured_at": value["captured_at"],
                "source": value["source"],
                "monthly_budget": value.get("monthly_budget"),
                "price_snapshot_ref": value.get("price_snapshot_ref"),
            }
        )
    except (KeyError, TypeError, ValueError) as error:
        raise ValueError("Verified pricing evidence has an invalid contract.") from error


def _approved_components(
    plan: models.InfrastructurePlan,
    azure_connection: models.UserAzureConnection,
    project: models.Project,
) -> tuple[list[ApprovedComponent], list[str]]:
    raw_components = (plan.plan_data or {}).get("components")
    if not isinstance(raw_components, list):
        raise ValueError("The approved plan has no component list.")
    components: list[ApprovedComponent] = []
    resource_types: list[str] = []
    approved_region = re.sub(r"[^a-z0-9]", "", str(plan.region).casefold())
    verified_region = re.sub(
        r"[^a-z0-9]",
        "",
        str(azure_connection.region or "").casefold(),
    )
    if not approved_region or approved_region != verified_region:
        raise ValueError(
            "The approved region no longer matches the verified Linux App Service plan."
        )
    for raw in raw_components:
        if not isinstance(raw, Mapping) or raw.get("deployable") is not True:
            continue
        service = str(raw.get("service") or "").strip()
        service_resource_types = _RESOURCE_TYPES.get(service)
        if service_resource_types is None:
            raise ValueError(f"The approved component '{service}' has no production Terraform renderer.")
        component_id = str(raw.get("id") or "").strip()
        tier = str(raw.get("tier") or "").strip() or None
        if service == "Azure App Service" and tier != str(azure_connection.app_service_plan or "").strip():
            raise ValueError("The approved App Service plan no longer matches the verified Azure target.")
        components.append(
            ApprovedComponent(
                id=component_id,
                service=service,
                tier=tier,
                properties={
                    "target_resource_group": deployment_targets.project_resource_group(project.id),
                    "existing_app_service_plan_name": azure_connection.app_service_plan,
                    "create_resource_group": True,
                    "public_network_access": True,
                    "managed_identity": "SystemAssigned",
                    "container_registry_role": "AcrPull",
                    "container_registry_scope": "configured-registry-only",
                },
            )
        )
        resource_types.extend(service_resource_types)
    if not components:
        raise ValueError("The approved plan contains no deployable component.")
    return components, sorted(set(resource_types))


def _application_name(project: models.Project) -> str:
    return deployment_targets.app_service_application_name(project.name, project.id)


def _terraform_inputs(
    project: models.Project,
    plan: models.InfrastructurePlan,
    azure_connection: models.UserAzureConnection,
) -> list[TerraformInputVariableV1]:
    subscription_id = str(azure_connection.subscription_id).strip()
    resource_group = str(azure_connection.resource_group).strip()
    plan_name = str(azure_connection.app_service_plan).strip()
    registry_server = str(azure_connection.acr_login_server).strip().casefold().rstrip("/")
    registry_match = _ACR_LOGIN_SERVER.fullmatch(registry_server)
    if registry_match is None:
        raise ValueError("The verified Azure target has an invalid container registry login server.")
    resource_prefix = f"/subscriptions/{subscription_id}/resourceGroups/{resource_group}/providers"
    return [
        TerraformInputVariableV1(name="application_name", type="string", value=_application_name(project)),
        TerraformInputVariableV1(
            name="app_service_plan_id",
            type="string",
            value=f"{resource_prefix}/Microsoft.Web/serverFarms/{plan_name}",
        ),
        TerraformInputVariableV1(
            name="container_registry_id",
            type="string",
            value=(
                f"{resource_prefix}/Microsoft.ContainerRegistry/registries/"
                f"{registry_match.group('name')}"
            ),
        ),
        TerraformInputVariableV1(name="location", type="string", value=plan.region),
        TerraformInputVariableV1(name="resource_group_name", type="string", value=deployment_targets.project_resource_group(project.id)),
    ]


def _artifact_reference(artifact: models.Artifact) -> ArtifactReferenceV1:
    return ArtifactReferenceV1(
        artifact_id=str(artifact.id),
        account_url=config.ARTIFACT_STORAGE_ACCOUNT_URL,
        container=artifact.storage_container,
        blob_name=artifact.storage_path,
        version_id=None,
        sha256=artifact.sha256_digest,
        size_bytes=artifact.size_bytes,
        media_type=artifact.content_type,
        classification="tenant-plan-sanitized",
    )


async def enqueue_approved_plan(
    db: AsyncSession,
    *,
    store: artifacts.ArtifactStore,
    tenant: models.Tenant,
    user: models.User,
    project: models.Project,
    plan: models.InfrastructurePlan,
    azure_connection: models.UserAzureConnection,
) -> QueuedTerraformGeneration:
    """Persist an approved request and transactionally enqueue generation."""

    if project.user_id != user.id or plan.project_id != project.id or plan.user_id != user.id:
        raise ValueError("The infrastructure plan is outside the authenticated project boundary.")
    if plan.status != "approved" or plan.provider != "azure":
        raise ValueError("Only an approved Azure infrastructure plan can be queued.")
    if not deployment_targets.has_verified_app_service_target(azure_connection):
        raise ValueError("The Azure deployment target must be connected and reverified before generation.")
    if azure_connection.user_id != user.id:
        raise ValueError("The Azure deployment target is outside the authenticated user boundary.")

    components, allowed_resource_types = _approved_components(plan, azure_connection, project)
    plan_digest = approved_plan_digest(plan)
    request = TerraformGenerationRequest(
        schema_version="terraform-generation-request.v1",
        tenant_id=tenant.id,
        project_id=project.id,
        plan_id=plan.id,
        plan_revision=plan.revision,
        plan_sha256=plan_digest,
        plan_status="approved",
        target_cloud="azure",
        region=plan.region,
        components=components,
        allowed_resource_types=allowed_resource_types,
        module_catalog_version=MODULE_CATALOG_VERSION,
        policy_version=POLICY_VERSION,
        constraints=[
            "Create exactly one project resource group using the supplied resource_group_name; reuse the verified existing Linux App Service plan and container registry in their existing hosting resource group.",
            "Create exactly one system-assigned Linux Web App and one AcrPull role assignment scoped to the verified existing container registry.",
            "Do not create credentials, additional resource groups, service plans, registries, or any other role assignment.",
            "Use deterministic ZeroOps names and standard tags.",
            "Keep non-secret runtime values in the supplied Terraform input-variable contract.",
        ],
        pricing=_verified_pricing(plan),
    )
    scope_digest = canonical_digest(
        {
            "components": [item.model_dump(mode="json") for item in components],
            "allowed_resource_types": allowed_resource_types,
            "target_resource_group": deployment_targets.project_resource_group(project.id),
        }
    )
    policy_digest = canonical_digest(
        {
            "policy_version": POLICY_VERSION,
            "maximum_resource_changes": config.TERRAFORM_MAX_RESOURCE_CHANGES,
            "maximum_delete_count": config.TERRAFORM_MAX_DELETE_COUNT,
            "maximum_replace_count": config.TERRAFORM_MAX_REPLACE_COUNT,
        }
    )
    run = await history.create_operation_run(
        db,
        tenant_id=tenant.id,
        requested_by_user_id=user.id,
        operation_type="infrastructure_pipeline",
        project_id=project.id,
        input_digest=plan_digest,
        idempotency_key=f"terraform-generation:{plan.id}:{plan.revision}",
        summary={
            "approved_plan_id": str(plan.id),
            "approved_plan_revision": plan.revision,
            "approved_plan_digest": plan_digest,
            "target_fingerprint": azure_connection.deployment_target_fingerprint,
            "scope_digest": scope_digest,
            "policy_digest": policy_digest,
        },
    )
    existing_outbox_result = await db.execute(
        select(models.WorkflowOutboxMessage).where(
            models.WorkflowOutboxMessage.operation_run_id == run.id,
            models.WorkflowOutboxMessage.queue_name == "terraform-generation",
        )
    )
    existing_outbox = existing_outbox_result.scalars().first()
    if existing_outbox is not None:
        artifact_result = await db.execute(
            select(models.Artifact).where(
                models.Artifact.operation_run_id == run.id,
                models.Artifact.kind == "approved-plan-request",
            )
        )
        existing_artifact = artifact_result.scalars().first()
        if existing_artifact is None:
            raise ValueError("The existing Terraform generation command has no approved-plan artifact.")
        return QueuedTerraformGeneration(
            operation_run_id=run.id,
            outbox_message_id=existing_outbox.id,
            plan_digest=plan_digest,
            artifact_id=existing_artifact.id,
            idempotent=True,
        )

    request_artifact = await artifacts.persist_user_artifact(
        db,
        store=store,
        tenant_id=tenant.id,
        operation_run_id=run.id,
        created_by_user_id=user.id,
        project_id=project.id,
        kind="approved-plan-request",
        display_name=f"approved-plan-r{plan.revision}.json",
        content_type="application/json",
        data=canonical_json_bytes(request.model_dump(mode="json")),
        metadata={
            "plan_id": str(plan.id),
            "plan_revision": plan.revision,
            "plan_digest": plan_digest,
            "scope_digest": scope_digest,
            "policy_digest": policy_digest,
        },
    )
    job_id = uuid.uuid5(run.id, "terraform-generation-job.v1")
    input_variables = _terraform_inputs(project, plan, azure_connection)
    job = TerraformGenerationJobV1(
        schema_version="terraform-generation-job.v1",
        job_id=str(job_id),
        tenant_id=str(tenant.id),
        project_id=str(project.id),
        run_id=str(run.id),
        correlation_id=str(run.id),
        attempt=1,
        enqueued_at=datetime.now(timezone.utc),
        user_id=str(user.id),
        approved_plan_artifact=_artifact_reference(request_artifact),
        output_artifact_id=str(uuid.uuid5(run.id, "terraform-generation-output.v1")),
        output_container=store.container_for_tenant(tenant.id),
        approved_plan_id=str(plan.id),
        approved_plan_revision=plan.revision,
        approved_plan_digest=plan_digest,
        target_environment="production",
        target_subscription_id=str(azure_connection.subscription_id),
        target_tenant_id=str(azure_connection.tenant_id),
        target_resource_group=deployment_targets.project_resource_group(project.id),
        terraform_version=TERRAFORM_VERSION,
        input_variables=input_variables,
        maximum_resource_changes=config.TERRAFORM_MAX_RESOURCE_CHANGES,
        maximum_delete_count=config.TERRAFORM_MAX_DELETE_COUNT,
        maximum_replace_count=config.TERRAFORM_MAX_REPLACE_COUNT,
    )
    outbox = await workflow_outbox.enqueue(
        db,
        tenant_id=tenant.id,
        operation_run_id=run.id,
        queue_name="terraform-generation",
        payload=job.model_dump(mode="json"),
        message_id=str(job_id),
        correlation_id=str(run.id),
    )
    return QueuedTerraformGeneration(
        operation_run_id=run.id,
        outbox_message_id=outbox.id,
        plan_digest=plan_digest,
        artifact_id=request_artifact.id,
        idempotent=False,
    )


def _require_digest(value: Any, *, field: str) -> str:
    normalized = str(value or "").strip().lower()
    if not _HEX_64.fullmatch(normalized):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"The Terraform plan has no valid {field}.")
    return normalized


def _expected_matches(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> None:
    mismatches = [key for key, value in actual.items() if expected.get(key) != value]
    if mismatches:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The Terraform plan, policy, variables, or cost changed after it was reviewed.",
        )


def _validated_plan_summary(
    plan_result: models.TerraformPlanResult,
    guardrails: ExecutionGuardrailsV1,
) -> tuple[dict[str, int], list[str], list[dict[str, Any]]]:
    summary = plan_result.plan_summary
    if not isinstance(summary, Mapping):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The Terraform plan has no validated resource summary.",
        )
    actions_value = summary.get("actions")
    kinds_value = summary.get("resource_kinds")
    if not isinstance(actions_value, Mapping) or set(actions_value) != set(_PLAN_ACTIONS):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The Terraform plan action summary is incomplete.",
        )
    actions: dict[str, int] = {}
    for name in _PLAN_ACTIONS:
        value = actions_value.get(name)
        if isinstance(value, bool) or not isinstance(value, int) or not 0 <= value <= 500:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The Terraform plan action summary is invalid.",
            )
        actions[name] = value
    if (
        not isinstance(kinds_value, list)
        or any(not isinstance(item, str) for item in kinds_value)
        or kinds_value != sorted(kinds_value)
        or len(kinds_value) != len(set(kinds_value))
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The Terraform plan resource summary is invalid.",
        )
    resource_kinds = list(kinds_value)
    if not set(resource_kinds).issubset(set(guardrails.allowed_resource_types)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The Terraform plan contains a resource type outside the approved allowlist.",
        )
    changes_value = summary.get("changes")
    if not isinstance(changes_value, list) or len(changes_value) > 500:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The Terraform plan has no bounded review-safe change list.",
        )
    changes: list[dict[str, Any]] = []
    counted_actions = {name: 0 for name in _PLAN_ACTIONS}
    sequence_to_action = {
        ("create",): "create",
        ("update",): "update",
        ("delete",): "delete",
        ("delete", "create"): "replace",
        ("create", "delete"): "replace",
        ("read",): "read",
        ("no-op",): "no_op",
    }
    for item in changes_value:
        if not isinstance(item, Mapping) or set(item) != {"address", "type", "actions"}:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The Terraform plan change list is invalid.",
            )
        address = item.get("address")
        resource_type = item.get("type")
        change_actions = item.get("actions")
        action_name = (
            sequence_to_action.get(tuple(change_actions))
            if isinstance(change_actions, list) and all(isinstance(value, str) for value in change_actions)
            else None
        )
        if (
            not isinstance(address, str)
            or not re.fullmatch(r"azurerm_[a-z0-9_]+\.[A-Za-z0-9_-]+", address)
            or not isinstance(resource_type, str)
            or resource_type not in guardrails.allowed_resource_types
            or action_name is None
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The Terraform plan change list is invalid.",
            )
        counted_actions[action_name] += 1
        changes.append(
            {
                "address": address,
                "type": resource_type,
                "actions": list(change_actions),
            }
        )
    if (
        changes != sorted(changes, key=lambda item: (item["address"], item["type"], item["actions"]))
        or len({item["address"] for item in changes}) != len(changes)
        or counted_actions != actions
        or sorted({item["type"] for item in changes}) != resource_kinds
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The Terraform plan change list does not match its action summary.",
        )
    total_changes = sum(actions[name] for name in ("create", "update", "delete", "replace"))
    if (
        total_changes > guardrails.maximum_resource_changes
        or actions["delete"] > guardrails.maximum_delete_count
        or actions["replace"] > guardrails.maximum_replace_count
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The Terraform plan exceeds its approved change guardrails.",
        )
    return actions, resource_kinds, changes


def review_safe_plan_summary(plan_result: models.TerraformPlanResult) -> dict[str, Any]:
    """Return only the bounded address/type/action view an owner can approve."""

    try:
        guardrails = ExecutionGuardrailsV1.model_validate(plan_result.guardrails)
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The Terraform plan guardrails are invalid.",
        ) from error
    actions, resource_kinds, changes = _validated_plan_summary(plan_result, guardrails)
    value: dict[str, Any] = {
        "actions": actions,
        "resource_kinds": resource_kinds,
        "changes": changes,
    }
    summary = plan_result.plan_summary if isinstance(plan_result.plan_summary, Mapping) else {}
    for field in ("terraform_version", "format_version"):
        candidate = summary.get(field)
        if isinstance(candidate, str) and re.fullmatch(r"[0-9][0-9.]{0,31}", candidate):
            value[field] = candidate
    return value


async def issue_verified_cost_evidence(
    db: AsyncSession,
    *,
    store: artifacts.ArtifactStore,
    user: models.User,
    project: models.Project,
    tenant: models.Tenant,
    operation_run_id: uuid.UUID,
) -> VerifiedTerraformCost:
    """Issue immutable cost evidence only for a proven zero-fixed-cost delta.

    The current renderer can add an App Service application to an already
    verified existing plan. It cannot create or resize the billable plan. For
    every other resource type the method fails closed until a trusted pricing
    integration can supply exact evidence.
    """

    result = await db.execute(
        select(models.TerraformPlanResult, models.OperationRun)
        .join(models.OperationRun, models.OperationRun.id == models.TerraformPlanResult.operation_run_id)
        .where(
            models.TerraformPlanResult.operation_run_id == operation_run_id,
            models.TerraformPlanResult.tenant_id == tenant.id,
            models.TerraformPlanResult.project_id == project.id,
            models.OperationRun.requested_by_user_id == user.id,
        )
        .with_for_update()
    )
    row = result.first()
    if row is None or project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Terraform plan result not found.")
    plan_result, operation_run = row
    approval_result = await db.execute(
        select(models.TerraformApplyApproval.id).where(
            models.TerraformApplyApproval.operation_run_id == operation_run_id
        )
    )
    if approval_result.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cost evidence cannot change after the saved plan has been approved.",
        )

    checked_at = datetime.now(timezone.utc)
    try:
        existing_cost = VerifiedCostEstimateV1.model_validate(plan_result.cost_estimate)
    except (TypeError, ValueError):
        existing_cost = None
    if (
        existing_cost is not None
        and existing_cost.captured_at
        >= checked_at - timedelta(minutes=config.TERRAFORM_COST_EVIDENCE_MAX_AGE_MINUTES)
    ):
        artifact_result = await db.execute(
            select(models.Artifact).where(
                models.Artifact.operation_run_id == operation_run_id,
                models.Artifact.kind == "terraform-cost-evidence",
                models.Artifact.sha256_digest == existing_cost.artifact_sha256,
            )
        )
        artifact = artifact_result.scalars().first()
        if artifact is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="The stored cost estimate has no immutable evidence artifact.",
            )
        return VerifiedTerraformCost(
            operation_run_id=operation_run_id,
            artifact_id=artifact.id,
            artifact_sha256=existing_cost.artifact_sha256,
            currency=existing_cost.currency,
            monthly_cost_microunits=existing_cost.monthly_cost_microunits,
            captured_at=existing_cost.captured_at,
            idempotent=True,
        )

    try:
        bundle = BundleReferenceV1.model_validate(plan_result.bundle)
        variables = InputVariablesReferenceV1.model_validate(plan_result.input_variables)
        guardrails = ExecutionGuardrailsV1.model_validate(plan_result.guardrails)
        saved_plan = SavedPlanReferenceV1.model_validate(plan_result.saved_plan)
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The Terraform plan control record is invalid and cannot be priced.",
        ) from error
    if (
        saved_plan.plan_job_digest != plan_result.plan_job_digest
        or saved_plan.bundle_sha256 != bundle.sha256
        or saved_plan.input_variables_sha256 != variables.sha256
        or saved_plan.scope_digest != guardrails.scope_digest
        or saved_plan.policy_digest != guardrails.policy_digest
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The Terraform plan control digests do not match.",
        )
    expected_plan_prefix = f"tenants/{tenant.id}/workflows/{operation_run_id}/plans/"
    if not saved_plan.blob_name.startswith(expected_plan_prefix):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The saved Terraform plan is outside the tenant workflow prefix.",
        )
    actions, resource_kinds, changes = _validated_plan_summary(plan_result, guardrails)
    if not set(resource_kinds).issubset(_ZERO_INCREMENTAL_FIXED_COST_RESOURCE_TYPES):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Exact verified pricing is unavailable for one or more planned resource types.",
        )

    currency = guardrails.budget_currency or config.TERRAFORM_COST_DEFAULT_CURRENCY
    evidence = {
        "schema_version": "terraform-cost-evidence.v1",
        "operation_run_id": str(operation_run_id),
        "project_id": str(project.id),
        "plan_job_digest": plan_result.plan_job_digest,
        "plan_sha256": saved_plan.sha256,
        "bundle_sha256": bundle.sha256,
        "input_variables_sha256": variables.sha256,
        "scope_digest": guardrails.scope_digest,
        "policy_digest": guardrails.policy_digest,
        "resource_kinds": resource_kinds,
        "changes": changes,
        "actions": actions,
        "target_resource_group": guardrails.target_resource_group,
        "pricing_method": "existing-app-service-plan-incremental-fixed-cost.v1",
        "pricing_scope": (
            "Only the fixed monthly infrastructure delta is included. The verified existing "
            "App Service plan, traffic, bandwidth, domains, and external services are excluded."
        ),
        "currency": currency,
        "monthly_cost_microunits": 0,
        "captured_at": checked_at.isoformat().replace("+00:00", "Z"),
    }
    artifact_key = uuid.uuid5(operation_run_id, "terraform-cost-evidence.v1")
    version_result = await db.execute(
        select(func.max(models.Artifact.version)).where(
            models.Artifact.tenant_id == tenant.id,
            models.Artifact.artifact_key == artifact_key,
        )
    )
    artifact_version = int(version_result.scalar_one_or_none() or 0) + 1
    artifact = await artifacts.persist_user_artifact(
        db,
        store=store,
        tenant_id=tenant.id,
        operation_run_id=operation_run_id,
        created_by_user_id=user.id,
        project_id=project.id,
        kind="terraform-cost-evidence",
        display_name=f"terraform-cost-evidence-v{artifact_version}.json",
        content_type="application/json",
        data=canonical_json_bytes(evidence),
        artifact_key=artifact_key,
        version=artifact_version,
        metadata={
            "schema_version": "terraform-cost-evidence.v1",
            "plan_job_digest": plan_result.plan_job_digest,
            "plan_sha256": saved_plan.sha256,
            "currency": currency,
            "monthly_cost_microunits": 0,
        },
    )
    cost = VerifiedCostEstimateV1(
        artifact_sha256=artifact.sha256_digest,
        currency=currency,
        monthly_cost_microunits=0,
        captured_at=checked_at,
    )
    plan_result.cost_estimate = cost.model_dump(mode="json")
    await history.append_activity_event(
        db,
        tenant_id=tenant.id,
        operation_run_id=operation_run_id,
        actor_user_id=user.id,
        project_id=project.id,
        action="terraform.cost_evidence.issued",
        actor_type="system",
        details="Verified incremental fixed-cost evidence was issued for the exact saved plan.",
        event_data={
            "artifact_id": str(artifact.id),
            "artifact_sha256": artifact.sha256_digest,
            "plan_sha256": saved_plan.sha256,
            "currency": currency,
            "monthly_cost_microunits": 0,
        },
        external_event_id=f"terraform-cost-evidence:{artifact.id}",
    )
    return VerifiedTerraformCost(
        operation_run_id=operation_run_id,
        artifact_id=artifact.id,
        artifact_sha256=artifact.sha256_digest,
        currency=currency,
        monthly_cost_microunits=0,
        captured_at=checked_at,
        idempotent=False,
    )


async def approve_and_enqueue_apply(
    db: AsyncSession,
    *,
    user: models.User,
    project: models.Project,
    tenant: models.Tenant,
    operation_run_id: uuid.UUID,
    expected: Mapping[str, Any],
    azure_connection: models.UserAzureConnection,
) -> ConsumedTerraformApproval:
    """Atomically consume one human approval into one exact apply command."""

    result_query = await db.execute(
        select(models.TerraformPlanResult, models.OperationRun)
        .join(models.OperationRun, models.OperationRun.id == models.TerraformPlanResult.operation_run_id)
        .where(
            models.TerraformPlanResult.operation_run_id == operation_run_id,
            models.TerraformPlanResult.tenant_id == tenant.id,
            models.TerraformPlanResult.project_id == project.id,
            models.OperationRun.requested_by_user_id == user.id,
        )
        .with_for_update()
    )
    row = result_query.first()
    if row is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Terraform plan result not found.")
    plan_result, operation_run = row
    if project.user_id != user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Terraform plan result not found.")

    current_plan_result = await db.execute(
        select(models.InfrastructurePlan).where(
            models.InfrastructurePlan.project_id == project.id,
            models.InfrastructurePlan.user_id == user.id,
        )
    )
    current_plan = current_plan_result.scalars().first()
    if (
        current_plan is None
        or current_plan.status != "approved"
        or current_plan.revision != plan_result.revision
        or approved_plan_digest(current_plan) != operation_run.input_digest
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The approved architecture changed after Terraform planning; generate a new plan.",
        )
    summary = operation_run.summary if isinstance(operation_run.summary, Mapping) else {}
    if (
        not deployment_targets.has_verified_app_service_target(azure_connection)
        or azure_connection.user_id != user.id
        or summary.get("target_fingerprint") != azure_connection.deployment_target_fingerprint
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The verified Azure deployment target changed after Terraform planning.",
        )

    try:
        bundle = dict(plan_result.bundle)
        input_variables = dict(plan_result.input_variables)
        guardrails = dict(plan_result.guardrails)
        saved_plan = dict(plan_result.saved_plan)
        cost = VerifiedCostEstimateV1.model_validate(plan_result.cost_estimate)
    except (TypeError, ValueError) as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A current verified Terraform cost estimate is required before approval.",
        ) from error
    checked_at = datetime.now(timezone.utc)
    if cost.captured_at < checked_at - timedelta(minutes=config.TERRAFORM_COST_EVIDENCE_MAX_AGE_MINUTES):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The verified Terraform cost estimate expired; refresh it before approval.",
        )

    plan_sha256 = _require_digest(saved_plan.get("sha256"), field="saved-plan digest")
    actual_expected = {
        "plan_job_digest": _require_digest(plan_result.plan_job_digest, field="plan job digest"),
        "plan_sha256": plan_sha256,
        "bundle_sha256": _require_digest(bundle.get("sha256"), field="bundle digest"),
        "input_variables_sha256": _require_digest(input_variables.get("sha256"), field="input-variable digest"),
        "scope_digest": _require_digest(guardrails.get("scope_digest"), field="scope digest"),
        "policy_digest": _require_digest(guardrails.get("policy_digest"), field="policy digest"),
        "cost_estimate_sha256": cost.artifact_sha256,
        "currency": cost.currency,
        "monthly_cost_microunits": cost.monthly_cost_microunits,
    }
    _expected_matches(expected, actual_expected)
    budget = guardrails.get("monthly_budget_microunits")
    budget_currency = guardrails.get("budget_currency")
    if budget is not None and (
        isinstance(budget, bool)
        or not isinstance(budget, int)
        or cost.monthly_cost_microunits > budget
        or budget_currency != cost.currency
    ):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The verified Terraform cost exceeds or does not match the approved budget guardrail.",
        )

    existing_result = await db.execute(
        select(models.TerraformApplyApproval).where(
            models.TerraformApplyApproval.operation_run_id == operation_run_id
        )
    )
    existing = existing_result.scalars().first()
    if existing is not None:
        stored_expected = {
            "plan_job_digest": existing.plan_job_digest,
            "plan_sha256": existing.plan_sha256,
            "bundle_sha256": existing.bundle_sha256,
            "input_variables_sha256": existing.input_variables_sha256,
            "scope_digest": existing.scope_digest,
            "policy_digest": existing.policy_digest,
            "cost_estimate_sha256": existing.cost_estimate_sha256,
            "currency": existing.currency,
            "monthly_cost_microunits": existing.monthly_cost_microunits,
        }
        _expected_matches(expected, stored_expected)
        outbox_result = await db.execute(
            select(models.WorkflowOutboxMessage).where(
                models.WorkflowOutboxMessage.operation_run_id == operation_run_id,
                models.WorkflowOutboxMessage.queue_name == "terraform-apply",
            )
        )
        outbox = outbox_result.scalars().first()
        if outbox is None:
            raise HTTPException(status_code=409, detail="The consumed approval has no durable apply command.")
        return ConsumedTerraformApproval(operation_run_id, existing.id, existing.apply_job_id, outbox.id, True)

    approval_id = uuid.uuid5(operation_run_id, "terraform-apply-approval.v1")
    apply_job_id = uuid.uuid5(operation_run_id, "terraform-apply-job.v1")
    expires_at = checked_at + timedelta(minutes=config.TERRAFORM_APPROVAL_TTL_MINUTES)
    approval_contract = ApplyApprovalV1(
        approval_id=str(approval_id),
        decision="approved",
        approved_by=str(user.id),
        approved_at=checked_at,
        expires_at=expires_at,
        apply_job_id=str(apply_job_id),
        plan_job_digest=actual_expected["plan_job_digest"],
        plan_sha256=plan_sha256,
        plan_etag=str(saved_plan.get("etag") or ""),
        bundle_sha256=actual_expected["bundle_sha256"],
        input_variables_sha256=actual_expected["input_variables_sha256"],
        scope_digest=actual_expected["scope_digest"],
        policy_digest=actual_expected["policy_digest"],
        cost_estimate_sha256=cost.artifact_sha256,
        currency=cost.currency,
        monthly_cost_microunits=cost.monthly_cost_microunits,
    )
    material = {
        "schema_version": "1.0",
        "operation": "apply",
        "job_id": str(apply_job_id),
        "tenant_id": str(tenant.id),
        "project_id": str(project.id),
        "user_id": str(user.id),
        "workflow_id": str(operation_run_id),
        "revision": plan_result.revision,
        "bundle": bundle,
        "input_variables": input_variables,
        "guardrails": guardrails,
        "state_key": f"tenants/{tenant.id}/workspaces/{operation_run_id}/terraform.tfstate",
        "target_subscription_id": str(azure_connection.subscription_id),
        "target_tenant_id": str(azure_connection.tenant_id),
        "terraform_version": TERRAFORM_VERSION,
        "requested_at": checked_at.isoformat().replace("+00:00", "Z"),
        "saved_plan": saved_plan,
        "cost_estimate": cost.model_dump(mode="json"),
        "approval": approval_contract.model_dump(mode="json"),
    }
    payload = {**material, "job_digest": canonical_digest(material)}
    envelope = TerraformApplyEnvelopeV1.model_validate(payload)
    approval = models.TerraformApplyApproval(
        id=approval_id,
        tenant_id=tenant.id,
        project_id=project.id,
        operation_run_id=operation_run_id,
        approved_by_user_id=user.id,
        apply_job_id=apply_job_id,
        status="consumed",
        plan_job_digest=approval_contract.plan_job_digest,
        plan_sha256=approval_contract.plan_sha256,
        plan_etag=approval_contract.plan_etag,
        bundle_sha256=approval_contract.bundle_sha256,
        input_variables_sha256=approval_contract.input_variables_sha256,
        scope_digest=approval_contract.scope_digest,
        policy_digest=approval_contract.policy_digest,
        cost_estimate_sha256=approval_contract.cost_estimate_sha256,
        currency=approval_contract.currency,
        monthly_cost_microunits=approval_contract.monthly_cost_microunits,
        approved_at=checked_at,
        expires_at=expires_at,
        consumed_at=checked_at,
    )
    db.add(approval)
    outbox = await workflow_outbox.enqueue(
        db,
        tenant_id=tenant.id,
        operation_run_id=operation_run_id,
        queue_name="terraform-apply",
        payload=envelope.model_dump(mode="json"),
        message_id=str(apply_job_id),
        correlation_id=str(operation_run_id),
        session_id=str(operation_run_id),
    )
    await history.append_activity_event(
        db,
        tenant_id=tenant.id,
        operation_run_id=operation_run_id,
        actor_user_id=user.id,
        project_id=project.id,
        action="terraform.apply.approval_consumed",
        actor_type="user",
        details="The authenticated owner approved one exact saved Terraform plan for apply.",
        event_data={
            "approval_id": str(approval_id),
            "apply_job_id": str(apply_job_id),
            **actual_expected,
        },
        external_event_id=f"terraform-apply-approval:{approval_id}",
    )
    return ConsumedTerraformApproval(operation_run_id, approval_id, apply_job_id, outbox.id, False)


__all__ = [
    "ConsumedTerraformApproval",
    "QueuedTerraformGeneration",
    "VerifiedTerraformCost",
    "approved_plan_digest",
    "approve_and_enqueue_apply",
    "enqueue_approved_plan",
    "issue_verified_cost_evidence",
]
