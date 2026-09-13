"""Unit tests for the Microsoft Foundry Architecture Advisor provider and service."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
import pytest

from backend.contracts.architecture_advisor import (
    ArchitectureRecommendation,
    CitationEvidence,
    ComponentRecommendation,
)
from backend.services.foundry_advisor import (
    FoundryAdvisorClient,
    FoundryAdvisorError,
    FoundryAuthenticationError,
    FoundryAuthorizationError,
    build_sanitized_advisor_prompt,
    invoke_architecture_advisor,
)
from backend.services.providers.azure_foundry import (
    AzureFoundryProvider,
    extract_annotations,
)
from backend.services.providers.base import (
    ProviderConfiguration,
    ProviderCredentialUnavailableError,
    ProviderError,
    ProviderRequest,
)


class MockHTTPStatusError(Exception):
    def __init__(self, status_code: int, message: str = "Error"):
        super().__init__(message)
        self.status_code = status_code
        self.response = SimpleNamespace(
            status_code=status_code,
            headers={"Retry-After": "1"} if status_code == 429 else {},
        )


def _sample_agent_json():
    return json.dumps({
        "recommendation": "Deploy the application to Azure App Service (Linux) with Azure Database for PostgreSQL Flexible Server.",
        "confidence": "high",
        "assumptions": ["Stateless web backend", "Standard regional network egress"],
        "missing_information": ["Expected monthly active users"],
        "proposed_components": [
            {
                "id": "app-service",
                "role": "web-api",
                "service": "Azure App Service",
                "proposed_sku": "B1",
                "instance_count": 1,
                "reason": "Host the Python FastAPI application container.",
                "evidence": ["FastAPI detected in repository"],
                "security_requirements": ["Managed Identity enabled", "HTTPS only"],
                "availability_recovery": "Single instance",
                "cost_status": "low",
                "validation_required": ["App Service Plan quota"],
            },
            {
                "id": "database",
                "role": "database",
                "service": "Azure Database for PostgreSQL Flexible Server",
                "proposed_sku": "B1ms",
                "instance_count": 1,
                "reason": "Relational data persistence.",
                "evidence": ["PostgreSQL drivers detected"],
                "security_requirements": ["Private endpoint"],
                "availability_recovery": "Zone redundant standby",
                "cost_status": "medium",
                "validation_required": ["Subnet delegation"],
            },
            {
                "id": "k8s-cluster",
                "role": "container-orchestrator",
                "service": "Azure Kubernetes Service",
                "proposed_sku": "Standard_D2s_v5",
                "instance_count": 3,
                "reason": "Alternative microservices clustering.",
                "evidence": [],
                "security_requirements": [],
                "availability_recovery": None,
                "cost_status": "high",
                "validation_required": [],
            }
        ],
        "cost_status": "estimated",
        "cost_considerations": ["B1 App Service plan is cost-effective for MVP workloads."],
        "evidence_sources": [
            {
                "id": "cite-1",
                "source_type": "knowledge",
                "title": "ZeroOps App Service Architecture Guide",
                "citation": "ZeroOps uses Linux App Service with system-assigned identity.",
                "url": None
            }
        ],
        "validation_required": ["Azure subscription quota validation"],
    })


def test_successful_architecture_response_and_allowlist_enforcement():
    """Test successful architecture response parsing and deployable allowlist labeling."""
    mock_openai = MagicMock()
    mock_response = SimpleNamespace(
        output_text=_sample_agent_json(),
        annotations=[
            {
                "type": "url_citation",
                "url": "https://learn.microsoft.com/azure/app-service/",
                "title": "Azure App Service documentation",
            }
        ],
        model="gpt-5.6-terra",
        usage=SimpleNamespace(input_tokens=1500, output_tokens=600),
    )
    mock_openai.responses.create.return_value = mock_response

    client = FoundryAdvisorClient(
        endpoint="https://zeroops-aitest-resource.services.ai.azure.com/api/projects/zeroops-aitest",
        agent_name="zeroops-architecture-advisor",
        agent_version="2",
        openai_client=mock_openai,
    )

    repo_facts = {
        "framework": "FastAPI",
        "runtime": "python",
        "database_dependencies": ["postgresql"],
        "name": "demo-app",
    }

    rec = invoke_architecture_advisor(
        facts=repo_facts,
        project_name="demo-app",
        user_query="Recommend an Azure architecture",
        client=client,
    )

    assert isinstance(rec, ArchitectureRecommendation)
    assert rec.confidence == "high"
    assert "Azure App Service" in rec.recommendation
    assert rec.provenance["model"] == "gpt-5.6-terra"
    assert rec.provenance["agent_version"] == "2"

    # Check component allowlist filtering:
    # 1. Azure App Service -> deployable=True
    app_comp = next(c for c in rec.proposed_components if c.service == "Azure App Service")
    assert app_comp.deployable is True
    assert app_comp.status_note == "Supported by current engine"

    # 2. Azure Kubernetes Service -> deployable=False, marked advisory only
    aks_comp = next(c for c in rec.proposed_components if c.service == "Azure Kubernetes Service")
    assert aks_comp.deployable is False
    assert "Advisory recommendation — deployment automation not currently supported" in aks_comp.status_note

    # 3. Azure Database for PostgreSQL Flexible Server -> deployable=False
    db_comp = next(c for c in rec.proposed_components if "PostgreSQL" in c.service)
    assert db_comp.deployable is False
    assert "Advisory recommendation" in db_comp.status_note

    # Check unsupported_services list
    assert "Azure Kubernetes Service" in rec.unsupported_services
    assert "Azure Database for PostgreSQL Flexible Server" in rec.unsupported_services
    assert "Azure App Service" not in rec.unsupported_services

    # Check that citations include repo facts and web citation
    web_citations = [c for c in rec.evidence_sources if c.source_type == "web"]
    assert len(web_citations) >= 1
    assert "azure/app-service" in (web_citations[0].url or "")


def test_authentication_error_401():
    """Verify 401 Unauthorized raises FoundryAuthenticationError with Entra details."""
    mock_openai = MagicMock()
    mock_openai.responses.create.side_effect = MockHTTPStatusError(401, "Unauthorized")

    client = FoundryAdvisorClient(
        endpoint="https://zeroops-aitest-resource.services.ai.azure.com/api/projects/zeroops-aitest",
        agent_name="zeroops-architecture-advisor",
        agent_version="2",
        openai_client=mock_openai,
    )

    with pytest.raises(FoundryAuthenticationError) as exc_info:
        invoke_architecture_advisor(
            facts={"framework": "FastAPI"},
            client=client,
        )

    assert "Authentication to Microsoft Foundry failed" in str(exc_info.value)
    assert mock_openai.responses.create.call_count == 1


def test_permission_error_403_reports_rbac():
    """Verify 403 Forbidden raises FoundryAuthorizationError specifying Azure AI Developer role."""
    mock_openai = MagicMock()
    mock_openai.responses.create.side_effect = MockHTTPStatusError(403, "Forbidden")

    client = FoundryAdvisorClient(
        endpoint="https://zeroops-aitest-resource.services.ai.azure.com/api/projects/zeroops-aitest",
        agent_name="zeroops-architecture-advisor",
        agent_version="2",
        openai_client=mock_openai,
    )

    with pytest.raises(FoundryAuthorizationError) as exc_info:
        invoke_architecture_advisor(
            facts={"framework": "FastAPI"},
            client=client,
        )

    assert "Azure AI Developer" in str(exc_info.value)
    assert mock_openai.responses.create.call_count == 1


def test_empty_response_handling():
    """Verify empty response raises FoundryAdvisorError."""
    mock_openai = MagicMock()
    mock_response = SimpleNamespace(
        output_text="",
        annotations=[],
        model="gpt-5.6-terra",
        usage=SimpleNamespace(input_tokens=100, output_tokens=0),
    )
    mock_openai.responses.create.return_value = mock_response

    client = FoundryAdvisorClient(
        endpoint="https://zeroops-aitest-resource.services.ai.azure.com/api/projects/zeroops-aitest",
        agent_name="zeroops-architecture-advisor",
        agent_version="2",
        openai_client=mock_openai,
    )

    with pytest.raises(FoundryAdvisorError) as exc_info:
        invoke_architecture_advisor(
            facts={"framework": "FastAPI"},
            client=client,
        )

    assert "empty" in str(exc_info.value).lower()


def test_tool_citation_extraction():
    """Verify extraction and categorization of tool citations from response annotations."""
    mock_response = SimpleNamespace(
        annotations=[
            {
                "type": "file_citation",
                "file_id": "file-zeroops-knowledge-123",
                "text": "Azure App Service Linux containers support standard Dockerfiles.",
                "title": "zeroops-knowledge-master.md",
            },
            {
                "type": "url_citation",
                "url": "https://azure.microsoft.com/en-us/pricing/details/app-service/linux/",
                "title": "App Service Linux Pricing",
                "text": "App Service Linux B1 pricing tier",
            },
        ]
    )

    extracted = extract_annotations(mock_response)
    assert len(extracted) == 2

    # Check extracted annotations
    types = {ann["type"] for ann in extracted}
    assert "file_citation" in types
    assert "url_citation" in types


def test_prompt_sanitization_removes_secrets():
    """Verify private repository secrets, tokens, passwords, and envs are never sent to advisor."""
    raw_facts = {
        "framework": "FastAPI",
        "runtime": "python:3.11",
        "environment_variables": [
            "PORT",
            "DATABASE_PASSWORD_SUPER_SECRET",
            "ghp_token_invalid_format",
        ],
        "database_dependencies": ["postgresql"],
        "port": 8000,
    }

    sanitized_prompt = build_sanitized_advisor_prompt(
        facts=raw_facts,
        project_name="my-private-app",
        user_query="What architecture should we use?",
    )

    # Safe technical facts SHOULD appear
    assert "FastAPI" in sanitized_prompt
    assert "python:3.11" in sanitized_prompt
    assert "8000" in sanitized_prompt
    assert "postgresql" in sanitized_prompt
    assert "PORT" in sanitized_prompt

    # Malformed or non-uppercase token strings should be filtered out
    assert "ghp_token_invalid_format" not in sanitized_prompt


def test_approval_boundary_enforcement():
    """Verify that architecture advisor produces recommendations only and cannot execute Terraform."""
    mock_openai = MagicMock()
    mock_openai.responses.create.return_value = SimpleNamespace(
        output_text=_sample_agent_json(),
        annotations=[],
        model="gpt-5.6-terra",
        usage=SimpleNamespace(input_tokens=100, output_tokens=100),
    )

    client = FoundryAdvisorClient(
        endpoint="https://zeroops-aitest-resource.services.ai.azure.com/api/projects/zeroops-aitest",
        agent_name="zeroops-architecture-advisor",
        agent_version="2",
        openai_client=mock_openai,
    )

    result = invoke_architecture_advisor(
        facts={"framework": "FastAPI"},
        client=client,
    )

    # Output is strictly an ArchitectureRecommendation model
    assert isinstance(result, ArchitectureRecommendation)

    # Verify no Terraform state or apply code is generated or executed
    serialized = result.model_dump_json()
    assert "terraform {" not in serialized
    assert "resource \"azurerm_" not in serialized
    assert "terraform.tfstate" not in serialized


def test_azure_foundry_provider_429_backoff():
    """Verify AzureFoundryProvider handles 429 rate limit with bounded backoff."""
    config = ProviderConfiguration(
        provider="azure-foundry",
        endpoint="https://zeroops-aitest-resource.services.ai.azure.com/api/projects/zeroops-aitest",
        model="gpt-5.6-terra",
        agent_name="zeroops-architecture-advisor",
        max_input_chars=10_000,
        max_output_tokens=500,
    )

    mock_openai = MagicMock()
    mock_openai.responses.create.side_effect = MockHTTPStatusError(429, "Rate limit exceeded")

    provider = AzureFoundryProvider(config, openai_client=mock_openai)

    req = ProviderRequest(
        system_prompt="system",
        user_prompt="user",
        schema_name="Output",
        output_schema={"type": "object"},
        max_output_tokens=100,
    )

    with patch("time.sleep") as mock_sleep:
        with pytest.raises(ProviderError) as exc_info:
            provider.generate(req)

        assert "rate limit" in str(exc_info.value).lower()
        # Retries up to 2 times (3 total calls)
        assert mock_openai.responses.create.call_count == 3
        assert mock_sleep.call_count == 2


def test_real_responses_content_annotations_are_extracted():
    response = SimpleNamespace(output=[SimpleNamespace(content=[SimpleNamespace(
        type="output_text", annotations=[
            SimpleNamespace(type="file_citation", file_id="file-knowledge", filename="guide.md"),
            {"type": "url_citation", "url": "https://learn.microsoft.com/azure/", "title": "Azure"},
        ],
    )])])
    annotations = extract_annotations(response)
    assert [a["type"] for a in annotations] == ["file_citation", "url_citation"]
    assert annotations[0]["title"] == "guide.md"


def test_unstructured_answer_does_not_manufacture_components_or_provenance():
    response = SimpleNamespace(output_text="Do not choose App Service B1 without measurements.", output=[])
    api = MagicMock()
    api.responses.create.return_value = response
    result = invoke_architecture_advisor({}, client=FoundryAdvisorClient(openai_client=api))
    assert result.proposed_components == []
    assert result.assumptions == []
    assert result.cost_considerations == []
    assert result.provenance["model"] == "Not reported"
    assert result.provenance["file_search_used"] is False
    assert result.provenance["web_search_used"] is False


def test_model_claimed_citations_do_not_prove_tool_use():
    content = json.loads(_sample_agent_json())
    content["evidence_sources"] = [{"source_type": "knowledge", "citation": "Claimed retrieval"}]
    api = MagicMock()
    api.responses.create.return_value = SimpleNamespace(output_text=json.dumps(content), output=[])
    result = invoke_architecture_advisor({}, client=FoundryAdvisorClient(openai_client=api))
    assert result.provenance["file_search_used"] is False
    assert [c.source_type for c in result.evidence_sources] == ["repository"]


@pytest.mark.parametrize("kind", ["advisor", "unified", "provider"])
def test_all_foundry_clients_use_federation_and_agent_endpoint(monkeypatch, kind):
    from backend.services.zeroops_foundry import ZeroOpsFoundryClient
    from backend import config as settings

    credential = object()
    with patch("backend.services.foundry_identity.foundry_credential", return_value=credential), \
         patch("azure.ai.projects.AIProjectClient") as project:
        if kind == "advisor":
            client = FoundryAdvisorClient(agent_name="demo", agent_version="1")
            client.get_client()
            timeout = settings.FOUNDRY_REQUEST_TIMEOUT_SECONDS
        elif kind == "unified":
            client = ZeroOpsFoundryClient(agent_name="demo", agent_version="1", timeout_seconds=45)
            client._get_openai_client()
            timeout = 45
        else:
            client = AzureFoundryProvider(ProviderConfiguration(
                provider="azure-foundry", endpoint=settings.FOUNDRY_PROJECT_ENDPOINT,
                model="gpt-5.6-terra", agent_name="demo", agent_version="1", timeout_seconds=45,
            ))
            client._client()
            timeout = 45
        assert project.call_args.kwargs["credential"] is credential
        assert project.call_args.kwargs["allow_preview"] is True
        project.return_value.get_openai_client.assert_called_once_with(
            agent_name="demo", timeout=timeout, max_retries=0,
        )


def test_agent_component_text_fields_are_preserved_as_single_items():
    from backend.services.foundry_advisor import _parse_components_from_text
    content = {"proposed_components": [{
        "id": "web", "service": "Azure App Service for Linux", "role": "Runtime",
        "reason": "Docker was detected", "evidence": "Dockerfile",
        "security_requirements": "HTTPS", "validation_required": "Verify startup",
    }]}
    components = _parse_components_from_text(json.dumps(content))
    assert len(components) == 1
    assert components[0].evidence == ["Dockerfile"]
    assert components[0].security_requirements == ["HTTPS"]
    assert components[0].validation_required == ["Verify startup"]
    assert components[0].deployable is True


def test_cross_tenant_credential_exchanges_source_identity_for_target(monkeypatch):
    from backend import config
    from backend.services.foundry_identity import foundry_credential

    monkeypatch.setattr(config, "FOUNDRY_TARGET_TENANT_ID", "target-tenant")
    monkeypatch.setattr(config, "FOUNDRY_MULTITENANT_APP_CLIENT_ID", "bridge-app")
    monkeypatch.setattr(config, "FOUNDRY_MANAGED_IDENTITY_CLIENT_ID", "source-identity")
    with patch("azure.identity.ManagedIdentityCredential") as identity, patch("azure.identity.ClientAssertionCredential") as exchange:
        identity.return_value.get_token.return_value.token = "test-assertion"
        assert foundry_credential() is exchange.return_value
        identity.assert_called_once_with(client_id="source-identity")
        assert exchange.call_args.kwargs["tenant_id"] == "target-tenant"
        assert exchange.call_args.kwargs["client_id"] == "bridge-app"
        assert exchange.call_args.kwargs["func"]() == "test-assertion"
        identity.return_value.get_token.assert_called_once_with("api://AzureADTokenExchange/.default")


@pytest.mark.parametrize("status", ["incomplete", "failed", "cancelled"])
def test_incomplete_adviser_result_is_never_saved_as_success(status):
    response = SimpleNamespace(status=status, output_text='{"recommendation": "cut off')
    client = FoundryAdvisorClient(openai_client=SimpleNamespace(
        responses=SimpleNamespace(create=lambda **kwargs: response)))
    with pytest.raises(FoundryAdvisorError, match="did not complete"):
        invoke_architecture_advisor({"framework": "Express.js"}, client=client)
