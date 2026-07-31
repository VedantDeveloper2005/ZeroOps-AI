"""Security helpers for untrusted worker input and safe telemetry."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import PurePosixPath
from typing import Any, Final

from .ai_contracts import TerraformBundle, TerraformGenerationRequest


_SECRET_KEY = re.compile(
    r"(?:password|passwd|secret|token|authorization|api[_-]?key|"
    r"connection[_-]?string|private[_-]?key|sas|client[_-]?secret)",
    re.IGNORECASE,
)
_HIGH_ENTROPY = re.compile(r"(?<![A-Za-z0-9])[A-Za-z0-9+/=_-]{32,}(?![A-Za-z0-9])")
_FORBIDDEN_TERRAFORM: Final[tuple[tuple[str, re.Pattern[str]], ...]] = (
    ("local-exec provisioner", re.compile(r'(?i)provisioner\s+"local-exec"')),
    ("remote-exec provisioner", re.compile(r'(?i)provisioner\s+"remote-exec"')),
    ("file provisioner", re.compile(r'(?i)provisioner\s+"file"')),
    ("external data source", re.compile(r'(?i)data\s+"external"')),
    ("null_resource", re.compile(r'(?i)resource\s+"null_resource"')),
    ("AzAPI action", re.compile(r'(?i)resource\s+"azapi_resource_action"')),
    (
        "shell or download command",
        re.compile(r"(?i)\b(?:bash|powershell|pwsh|cmd\.exe|curl|wget)\b"),
    ),
    ("open internet CIDR", re.compile(r"(?i)(?:0\.0\.0\.0/0|::/0)")),
    (
        "Owner role assignment",
        re.compile(r'(?i)role_definition_name\s*=\s*"Owner"'),
    ),
    (
        "User Access Administrator assignment",
        re.compile(
            r'(?i)role_definition_name\s*=\s*"User Access Administrator"'
        ),
    ),
    (
        "embedded private key",
        re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"),
    ),
)
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
_SECRET_NAME = re.compile(
    r"(?i)(?:password|passwd|secret|token|api[_-]?key|private[_-]?key|client[_-]?secret)"
)
_CURRENCY_AMOUNT = re.compile(
    r"(?i)(?:[$\u20ac\u00a3\u20b9]\s*\d|\b(?:usd|eur|gbp|inr)\s*\d)"
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


class UnsafeArtifactError(ValueError):
    """Raised when an artifact violates a deterministic safety boundary."""


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def canonical_json_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        allow_nan=False,
    ).encode("utf-8")


def safe_relative_path(value: str, *, suffix: str = ".tf") -> str:
    normalized = value.replace("\\", "/")
    path = PurePosixPath(normalized)
    if (
        not normalized
        or normalized.startswith("/")
        or path.is_absolute()
        or ".." in path.parts
        or "." in path.parts
        or len(path.parts) > 8
        or len(normalized) > 240
    ):
        raise UnsafeArtifactError("Terraform file path is not a safe relative path")
    if not normalized.endswith(suffix):
        raise UnsafeArtifactError(f"Terraform file must end with {suffix}")
    return normalized


def validate_terraform_source(content: str) -> None:
    if len(content.encode("utf-8")) > 1_048_576:
        raise UnsafeArtifactError("A Terraform file exceeds the 1 MiB limit")
    for label, pattern in _FORBIDDEN_TERRAFORM:
        if pattern.search(content):
            raise UnsafeArtifactError(f"Terraform contains forbidden {label}")
    if _SECRET_KEY.search(content) and re.search(
        r"(?i)(?:default|value)\s*=\s*\"[^\"$]{8,}\"",
        content,
    ):
        raise UnsafeArtifactError("Terraform appears to embed a secret value")
    if re.search(r'(?i)\bprovider\s+"(?!azurerm\b)', content):
        raise UnsafeArtifactError("Terraform contains a non-allowlisted provider")


def _approved_public_network(request: TerraformGenerationRequest) -> bool:
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
    if safe_relative_path(path) not in _ALLOWED_ROOT_FILES:
        raise UnsafeArtifactError("Terraform bundle contains a disallowed root file")
    if "\x00" in content:
        raise UnsafeArtifactError("Terraform source contains an invalid null byte")
    validate_terraform_source(content)

    if _QUOTED_SECRET_ASSIGNMENT.search(content):
        raise UnsafeArtifactError("Terraform source contains a hardcoded secret-like value")

    for provider_name in _PROVIDER_DECLARATION.findall(content):
        if provider_name != "azurerm":
            raise UnsafeArtifactError("Terraform source declares a non-AzureRM provider")

    for backend_name in _BACKEND_DECLARATION.findall(content):
        if backend_name != "azurerm":
            raise UnsafeArtifactError("Terraform state backend must be AzureRM")

    for source in _SOURCE_ASSIGNMENT.findall(content):
        if source != "hashicorp/azurerm":
            raise UnsafeArtifactError(
                "Terraform v1 bundles cannot reference remote or unapproved modules"
            )
    if re.search(r'(?m)^\s*module\s+"', content):
        raise UnsafeArtifactError(
            "Terraform v1 bundles cannot declare modules outside the approved renderer"
        )

    allowed_resources = set(request.allowed_resource_types)
    for resource_type, _ in _RESOURCE_DECLARATION.findall(content):
        if resource_type not in allowed_resources:
            raise UnsafeArtifactError(
                "Terraform source declares a resource outside the approved allowlist"
            )

    for data_type, _ in _DATA_DECLARATION.findall(content):
        if data_type not in _SAFE_AZURERM_DATA_SOURCES:
            raise UnsafeArtifactError(
                "Terraform source declares an unapproved data source"
            )

    if not _approved_public_network(request):
        public_patterns = (
            re.compile(r"(?i)public_network_access_enabled\s*=\s*true"),
            re.compile(r"(?i)public_network_access\s*=\s*true"),
            re.compile(r"(?i)allow_nested_items_to_be_public\s*=\s*true"),
            re.compile(r"(?i)allow_blob_public_access\s*=\s*true"),
            re.compile(r'(?i)default_action\s*=\s*"Allow"'),
        )
        if any(pattern.search(content) for pattern in public_patterns):
            raise UnsafeArtifactError(
                "Terraform source enables public access that was not approved"
            )

    for match in re.finditer(
        r'(?is)variable\s+"([^"]+)"\s*\{(.*?)\}',
        content,
    ):
        variable_name, body = match.groups()
        if _SECRET_NAME.search(variable_name) and re.search(
            r"(?m)^\s*default\s*=",
            body,
        ):
            raise UnsafeArtifactError(
                "Secret-like Terraform variables cannot define defaults"
            )

    if path == "versions.tf":
        if "required_version" not in content or "required_providers" not in content:
            raise UnsafeArtifactError(
                "versions.tf must pin Terraform and AzureRM provider constraints"
            )
        if "hashicorp/azurerm" not in content:
            raise UnsafeArtifactError(
                "versions.tf must use the official AzureRM provider"
            )


def validate_terraform_bundle(
    bundle: TerraformBundle,
    request: TerraformGenerationRequest,
) -> TerraformBundle:
    """Fail closed unless model-authored Terraform matches the approved request."""

    if (
        bundle.plan_revision != request.plan_revision
        or bundle.plan_sha256 != request.plan_sha256
    ):
        raise UnsafeArtifactError(
            "Terraform output does not match the approved plan revision"
        )
    if bundle.status == "blocked":
        return bundle

    paths = {safe_relative_path(item.path) for item in bundle.files}
    if not paths.issubset(_ALLOWED_ROOT_FILES):
        raise UnsafeArtifactError("Terraform bundle contains a disallowed root file")
    if _REQUIRED_ROOT_FILES - paths:
        raise UnsafeArtifactError("Terraform bundle is missing required root files")

    component_ids = {component.id for component in request.components}
    allowed_resources = set(request.allowed_resource_types)
    for mapping in bundle.resources:
        if mapping.component_id not in component_ids:
            raise UnsafeArtifactError(
                "Terraform resource mapping references an unapproved component"
            )
        if mapping.resource_type not in allowed_resources:
            raise UnsafeArtifactError(
                "Terraform resource mapping references an unapproved resource type"
            )

    for optimization in bundle.cost_optimizations:
        if optimization.component_id not in component_ids:
            raise UnsafeArtifactError(
                "Terraform cost optimization references an unapproved component"
            )
        if request.pricing is None:
            if not optimization.requires_verified_pricing:
                raise UnsafeArtifactError(
                    "Unpriced Terraform recommendations must require verified pricing"
                )
            if _CURRENCY_AMOUNT.search(
                f"{optimization.mechanism} {optimization.tradeoff}"
            ):
                raise UnsafeArtifactError(
                    "Terraform output invents a numerical cost without verified pricing"
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
        raise UnsafeArtifactError(
            "Terraform variable metadata does not match the generated source"
        )
    if declared_outputs != metadata_outputs:
        raise UnsafeArtifactError(
            "Terraform output metadata does not match the generated source"
        )
    if declared_resources != metadata_resources:
        raise UnsafeArtifactError(
            "Terraform resource metadata does not match the generated source"
        )

    for variable in bundle.variables:
        if _SECRET_NAME.search(variable.name):
            if not variable.sensitive or variable.default is not None:
                raise UnsafeArtifactError(
                    "Secret-like variables must be sensitive and have no default"
                )

    validation_text = "\n".join(bundle.validation_requirements).lower()
    required_checks = (
        "terraform fmt",
        "terraform init",
        "terraform validate",
        "terraform plan",
        "human approval",
        "pricing",
    )
    if any(check not in validation_text for check in required_checks):
        raise UnsafeArtifactError(
            "Terraform bundle omits a mandatory deterministic validation step"
        )
    if "tflint" not in validation_text or "checkov" not in validation_text:
        raise UnsafeArtifactError(
            "Terraform bundle omits mandatory lint or security validation"
        )
    return bundle


def redact(value: Any, *, depth: int = 0) -> Any:
    """Return a bounded JSON-safe value with likely secrets removed."""

    if depth > 6:
        return "[TRUNCATED]"
    if isinstance(value, dict):
        safe: dict[str, Any] = {}
        for index, (key, child) in enumerate(value.items()):
            if index >= 40:
                safe["_truncated"] = True
                break
            key_text = str(key)[:128]
            safe[key_text] = "[REDACTED]" if _SECRET_KEY.search(key_text) else redact(
                child,
                depth=depth + 1,
            )
        return safe
    if isinstance(value, list):
        return [redact(item, depth=depth + 1) for item in value[:100]]
    if isinstance(value, str):
        bounded = value[:2048]
        return _HIGH_ENTROPY.sub("[REDACTED]", bounded)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:512]
