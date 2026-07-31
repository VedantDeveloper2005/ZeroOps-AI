"""Fail-closed AI-assisted Terraform bundle generation and safety checks."""

from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath
from typing import Final

from backend.contracts.ai import (
    AIWorkload,
    ModelProvenance,
    TerraformBundle,
    TerraformGenerationRequest,
)
from backend.services.model_gateway import (
    ModelGateway,
    StructuredGenerationResult,
)


class TerraformGenerationError(RuntimeError):
    """Safe failure raised before any Terraform artifact can be executed."""


class TerraformSafetyError(TerraformGenerationError):
    """Raised when generated source violates deterministic safety policy."""


_AI_SPEC_ROOT: Final[Path] = Path(__file__).resolve().parents[2] / "ai-specs"
_ALLOWED_ROOT_FILES: Final[set[str]] = {
    "versions.tf",
    "providers.tf",
    "variables.tf",
    "locals.tf",
    "main.tf",
    "outputs.tf",
}
_REQUIRED_ROOT_FILES: Final[set[str]] = {
    "versions.tf",
    "providers.tf",
    "variables.tf",
    "main.tf",
    "outputs.tf",
}
_SAFE_AZURERM_DATA_SOURCES: Final[set[str]] = {
    "azurerm_client_config",
    "azurerm_resource_group",
    "azurerm_subscription",
}
_SECRET_NAME_PATTERN = re.compile(
    r"(?i)(?:password|passwd|secret|token|api[_-]?key|private[_-]?key|client[_-]?secret)"
)
_CURRENCY_AMOUNT_PATTERN = re.compile(
    r"(?i)(?:[$€£₹]\s*\d|\b(?:usd|eur|gbp|inr)\s*\d)"
)
_RESOURCE_DECLARATION = re.compile(
    r'(?m)^\s*resource\s+"(azurerm_[a-z0-9_]+)"\s+"([A-Za-z0-9_-]+)"\s*\{'
)
_DATA_DECLARATION = re.compile(
    r'(?m)^\s*data\s+"([a-z0-9_]+)"\s+"([A-Za-z0-9_-]+)"\s*\{'
)
_VARIABLE_DECLARATION = re.compile(
    r'(?m)^\s*variable\s+"([a-z][a-z0-9_]*)"\s*\{'
)
_OUTPUT_DECLARATION = re.compile(
    r'(?m)^\s*output\s+"([a-z][a-z0-9_]*)"\s*\{'
)
_PROVIDER_DECLARATION = re.compile(
    r'(?m)^\s*provider\s+"([a-z0-9_-]+)"\s*\{'
)
_BACKEND_DECLARATION = re.compile(
    r'(?m)^\s*backend\s+"([a-z0-9_-]+)"\s*\{'
)
_SOURCE_ASSIGNMENT = re.compile(r'(?m)^\s*source\s*=\s*"([^"]+)"')
_QUOTED_SECRET_ASSIGNMENT = re.compile(
    r'(?im)^\s*[a-z0-9_]*(?:password|passwd|secret|token|api_key|private_key|client_secret)[a-z0-9_]*'
    r'\s*=\s*"[^"]+"'
)

_FORBIDDEN_SOURCE_PATTERNS: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("local-exec provisioner", re.compile(r'(?i)provisioner\s+"local-exec"')),
    ("remote-exec provisioner", re.compile(r'(?i)provisioner\s+"remote-exec"')),
    ("file provisioner", re.compile(r'(?i)provisioner\s+"file"')),
    ("external data source", re.compile(r'(?i)data\s+"external"')),
    ("null_resource", re.compile(r'(?i)resource\s+"null_resource"')),
    ("AzAPI action", re.compile(r'(?i)resource\s+"azapi_resource_action"')),
    ("shell command interpolation", re.compile(r"(?i)\b(?:bash|powershell|cmd\.exe|curl|wget)\b")),
    ("open internet CIDR", re.compile(r'(?i)(?:0\.0\.0\.0/0|::/0)')),
    ("owner role assignment", re.compile(r'(?i)role_definition_name\s*=\s*"Owner"')),
    (
        "User Access Administrator assignment",
        re.compile(r'(?i)role_definition_name\s*=\s*"User Access Administrator"'),
    ),
    ("embedded PEM material", re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----")),
)


def load_terraform_instructions() -> str:
    path = _AI_SPEC_ROOT / "terraform-generation" / "instructions.md"
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError as error:
        raise TerraformGenerationError(
            "Terraform generation instructions are unavailable."
        ) from error
    if not value:
        raise TerraformGenerationError("Terraform generation instructions are empty.")
    return value


def _safe_path(value: str) -> str:
    if "\\" in value:
        raise TerraformSafetyError("Terraform bundle paths must use forward slashes.")
    path = PurePosixPath(value)
    if (
        path.is_absolute()
        or len(path.parts) != 1
        or any(part in {"", ".", ".."} for part in path.parts)
        or value not in _ALLOWED_ROOT_FILES
    ):
        raise TerraformSafetyError("Terraform bundle contains a disallowed file path.")
    return value


def _public_network_was_approved(request: TerraformGenerationRequest) -> bool:
    return any(
        component.properties.get("public_network_access") is True
        for component in request.components
    )


def _validate_source_file(
    *,
    path: str,
    content: str,
    request: TerraformGenerationRequest,
) -> None:
    if "\x00" in content:
        raise TerraformSafetyError("Terraform source contains an invalid null byte.")

    for label, pattern in _FORBIDDEN_SOURCE_PATTERNS:
        if pattern.search(content):
            raise TerraformSafetyError(f"Terraform source contains forbidden {label}.")

    if _QUOTED_SECRET_ASSIGNMENT.search(content):
        raise TerraformSafetyError("Terraform source contains a hardcoded secret-like value.")

    for provider_name in _PROVIDER_DECLARATION.findall(content):
        if provider_name != "azurerm":
            raise TerraformSafetyError("Terraform source declares a non-Azure provider.")

    for backend_name in _BACKEND_DECLARATION.findall(content):
        if backend_name != "azurerm":
            raise TerraformSafetyError("Terraform state backend must be AzureRM.")

    for source in _SOURCE_ASSIGNMENT.findall(content):
        if source != "hashicorp/azurerm":
            raise TerraformSafetyError(
                "Terraform v1 bundles cannot reference remote or unapproved modules."
            )

    if re.search(r'(?m)^\s*module\s+"', content):
        raise TerraformSafetyError(
            "Terraform v1 bundles cannot declare modules outside the approved renderer."
        )

    allowed_resources = set(request.allowed_resource_types)
    for resource_type, _ in _RESOURCE_DECLARATION.findall(content):
        if resource_type not in allowed_resources:
            raise TerraformSafetyError(
                "Terraform source declares a resource outside the approved allowlist."
            )

    for data_type, _ in _DATA_DECLARATION.findall(content):
        if data_type not in _SAFE_AZURERM_DATA_SOURCES:
            raise TerraformSafetyError(
                "Terraform source declares an unapproved data source."
            )

    if not _public_network_was_approved(request):
        public_network_patterns = (
            re.compile(r"(?i)public_network_access_enabled\s*=\s*true"),
            re.compile(r"(?i)public_network_access\s*=\s*true"),
            re.compile(r"(?i)allow_nested_items_to_be_public\s*=\s*true"),
            re.compile(r"(?i)allow_blob_public_access\s*=\s*true"),
            re.compile(r'(?i)default_action\s*=\s*"Allow"'),
        )
        if any(pattern.search(content) for pattern in public_network_patterns):
            raise TerraformSafetyError(
                "Terraform source enables public access that was not approved."
            )

    # Secret variables must never acquire defaults in source, even if the
    # model's metadata claims the value is sensitive.
    for match in re.finditer(
        r'(?is)variable\s+"([^"]+)"\s*\{(.*?)\}',
        content,
    ):
        variable_name, body = match.groups()
        if _SECRET_NAME_PATTERN.search(variable_name) and re.search(r"(?m)^\s*default\s*=", body):
            raise TerraformSafetyError(
                "Secret-like Terraform variables cannot define defaults."
            )

    if path == "versions.tf":
        if "required_version" not in content or "required_providers" not in content:
            raise TerraformSafetyError(
                "versions.tf must pin Terraform and AzureRM provider constraints."
            )
        if "hashicorp/azurerm" not in content:
            raise TerraformSafetyError("versions.tf must use the official AzureRM provider.")


def validate_terraform_bundle(
    bundle: TerraformBundle,
    request: TerraformGenerationRequest,
) -> TerraformBundle:
    """Validate generated source against the immutable approved plan contract."""
    if bundle.plan_revision != request.plan_revision or bundle.plan_sha256 != request.plan_sha256:
        raise TerraformSafetyError(
            "Terraform output does not match the approved plan revision."
        )

    if bundle.status == "blocked":
        return bundle

    paths = {_safe_path(item.path) for item in bundle.files}
    missing = _REQUIRED_ROOT_FILES - paths
    if missing:
        raise TerraformSafetyError(
            "Terraform bundle is missing required root files."
        )

    approved_component_ids = {component.id for component in request.components}
    allowed_resources = set(request.allowed_resource_types)
    for mapping in bundle.resources:
        if mapping.component_id not in approved_component_ids:
            raise TerraformSafetyError(
                "Terraform resource mapping references an unapproved component."
            )
        if mapping.resource_type not in allowed_resources:
            raise TerraformSafetyError(
                "Terraform resource mapping references an unapproved resource type."
            )

    for optimization in bundle.cost_optimizations:
        if optimization.component_id not in approved_component_ids:
            raise TerraformSafetyError(
                "Terraform cost optimization references an unapproved component."
            )
        if request.pricing is None:
            if not optimization.requires_verified_pricing:
                raise TerraformSafetyError(
                    "Unpriced Terraform recommendations must require verified pricing."
                )
            if _CURRENCY_AMOUNT_PATTERN.search(
                f"{optimization.mechanism} {optimization.tradeoff}"
            ):
                raise TerraformSafetyError(
                    "Terraform output invents a numerical cost without verified pricing."
                )

    metadata_variables = {item.name for item in bundle.variables}
    metadata_outputs = {item.name for item in bundle.outputs}
    metadata_resources = {item.address for item in bundle.resources}
    declared_variables: set[str] = set()
    declared_outputs: set[str] = set()
    declared_resources: set[str] = set()

    for item in bundle.files:
        _validate_source_file(path=item.path, content=item.content, request=request)
        declared_variables.update(_VARIABLE_DECLARATION.findall(item.content))
        declared_outputs.update(_OUTPUT_DECLARATION.findall(item.content))
        declared_resources.update(
            f"{resource_type}.{name}"
            for resource_type, name in _RESOURCE_DECLARATION.findall(item.content)
        )

    if declared_variables != metadata_variables:
        raise TerraformSafetyError(
            "Terraform variable metadata does not match the generated source."
        )
    if declared_outputs != metadata_outputs:
        raise TerraformSafetyError(
            "Terraform output metadata does not match the generated source."
        )
    if declared_resources != metadata_resources:
        raise TerraformSafetyError(
            "Terraform resource metadata does not match the generated source."
        )

    for variable in bundle.variables:
        if _SECRET_NAME_PATTERN.search(variable.name):
            if not variable.sensitive or variable.default is not None:
                raise TerraformSafetyError(
                    "Secret-like variables must be sensitive and have no default."
                )

    validation_text = "\n".join(bundle.validation_requirements).lower()
    for required_check in (
        "terraform fmt",
        "terraform init",
        "terraform validate",
        "terraform plan",
        "human approval",
        "pricing",
    ):
        if required_check not in validation_text:
            raise TerraformSafetyError(
                "Terraform bundle omits a mandatory deterministic validation step."
            )
    if "tflint" not in validation_text or "checkov" not in validation_text:
        raise TerraformSafetyError(
            "Terraform bundle omits mandatory lint or security validation."
        )

    return bundle


def generate_terraform_bundle(
    request: TerraformGenerationRequest,
    *,
    gateway: ModelGateway | None = None,
) -> StructuredGenerationResult[TerraformBundle]:
    """Generate a Terraform bundle; never plan, apply, or execute it."""
    model_gateway = gateway or ModelGateway()
    result = model_gateway.generate_structured(
        workload=AIWorkload.TERRAFORM_GENERATION,
        system_prompt=load_terraform_instructions(),
        user_prompt=json.dumps(
            request.model_dump(mode="json"),
            sort_keys=True,
            separators=(",", ":"),
        ),
        output_contract=TerraformBundle,
    )
    if result.value is None:
        # The gateway already fails closed for this workload. Keep the guard in
        # case a custom gateway violates that invariant.
        raise TerraformGenerationError(
            "Terraform generation returned no validated bundle."
        )
    validate_terraform_bundle(result.value, request)
    return result


__all__ = [
    "ModelProvenance",
    "TerraformGenerationError",
    "TerraformSafetyError",
    "generate_terraform_bundle",
    "load_terraform_instructions",
    "validate_terraform_bundle",
]
