"""Unit tests for the centralized ZeroOps Foundry Client service."""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock
import pytest
from pydantic import BaseModel

from backend.services.zeroops_foundry import (
    ZeroOpsFoundryClient,
    FoundryAgentError,
    FoundryAuthenticationError,
    FoundryAuthorizationError,
    extract_json_from_text,
    get_foundry_client,
    set_foundry_client,
    TASK_REPOSITORY_ANALYSIS,
    TASK_ARCHITECTURE_RECOMMENDATION,
    TASK_ARCHITECTURE_CHAT,
    TASK_FAILURE_ANALYSIS,
    TASK_FIX_RECOMMENDATION,
    TASK_SECURITY_ANALYSIS,
    TASK_TERRAFORM_GENERATION,
    TASK_PIPELINE_EXPLANATION,
    TASK_COST_OPTIMIZATION,
    TASK_DEPLOYMENT_GUIDANCE,
)


class SampleContract(BaseModel):
    summary: str
    status: str


def _make_mock_client(output_text: str = "", status_code: int | None = None, side_effect: Exception | None = None):
    mock_openai = MagicMock()
    if side_effect:
        mock_openai.responses.create.side_effect = side_effect
    elif status_code:
        err = Exception(f"HTTP {status_code}")
        err.status_code = status_code
        mock_openai.responses.create.side_effect = err
    else:
        response = SimpleNamespace(
            output_text=output_text,
            usage=SimpleNamespace(input_tokens=50, output_tokens=25),
        )
        mock_openai.responses.create.return_value = response

    client = ZeroOpsFoundryClient(
        endpoint="https://zeroops-aitest-resource.services.ai.azure.com/api/projects/zeroops-aitest",
        agent_name="demo",
        agent_version="1",
        openai_client=mock_openai,
    )
    return client, mock_openai


def test_extract_json_from_plain_text():
    raw = '{"key": "value", "number": 42}'
    data = extract_json_from_text(raw)
    assert data == {"key": "value", "number": 42}


def test_extract_json_from_markdown_block():
    raw = "Here is the response:\n```json\n{\n  \"action\": \"allow\",\n  \"count\": 1\n}\n```\nDone."
    data = extract_json_from_text(raw)
    assert data == {"action": "allow", "count": 1}


def test_extract_json_invalid_raises():
    with pytest.raises(ValueError, match="No valid JSON object"):
        extract_json_from_text("This is purely conversational text without JSON.")


def test_call_agent_formats_prompt_and_agent_reference():
    client, mock_openai = _make_mock_client("Hello from demo agent!")
    reply, prov = client.call_agent(
        task_type=TASK_ARCHITECTURE_CHAT,
        user_input="Why App Service?",
        context="Current architecture: Azure App Service",
    )
    assert reply == "Hello from demo agent!"
    assert prov.provider == "azure-ai-foundry"
    assert prov.agent == "demo"
    assert prov.agent_version == "1"
    assert prov.execution_mode == "live"
    assert prov.ai_used is True

    mock_openai.responses.create.assert_called_once()
    call_kwargs = mock_openai.responses.create.call_args.kwargs
    assert call_kwargs["extra_body"]["agent_reference"] == {
        "name": "demo",
        "version": "1",
        "type": "agent_reference",
    }
    content = call_kwargs["input"][0]["content"]
    assert "TASK_TYPE: ARCHITECTURE_CHAT" in content
    assert "DEMO_MODE: true" in content
    assert "Current architecture: Azure App Service" in content
    assert "Why App Service?" in content


def test_call_agent_structured_validates_pydantic():
    client, _ = _make_mock_client('{"summary": "App review", "status": "approved"}')
    result, prov = client.call_agent_structured(
        task_type=TASK_REPOSITORY_ANALYSIS,
        user_input="Review repository",
        output_contract=SampleContract,
    )
    assert isinstance(result, SampleContract)
    assert result.summary == "App review"
    assert result.status == "approved"
    assert prov.ai_used is True


def test_analyze_repository_task():
    json_resp = json.dumps({
        "explanation": "Python web app",
        "deployment_risk": "None detected",
        "recommendations": ["Check DB connection"],
        "unresolved_questions": ["Confirm environment secrets"],
    })
    client, _ = _make_mock_client(json_resp)
    data, prov = client.analyze_repository(
        source_facts={"framework": "FastAPI", "port": 8000},
        safe_files=[{"path": "app.py", "content": "import fastapi"}],
        repo_tree="app.py\nrequirements.txt",
    )
    assert data["explanation"] == "Python web app"
    assert prov.task_type == TASK_REPOSITORY_ANALYSIS


def test_recommend_architecture_task():
    json_resp = json.dumps({
        "recommendation": "Use Azure App Service with PostgreSQL",
        "confidence": "high",
        "assumptions": ["Stateless web app"],
        "missing_information": [],
        "proposed_components": [
            {"id": "app", "role": "web", "service": "Azure App Service", "proposed_sku": "B1"}
        ],
        "cost_considerations": ["B1 provides cost effective compute"],
    })
    client, _ = _make_mock_client(json_resp)
    data, prov = client.recommend_architecture(
        facts={"framework": "FastAPI"},
        project_name="my-project",
    )
    assert data["confidence"] == "high"
    assert len(data["proposed_components"]) == 1
    assert prov.task_type == TASK_ARCHITECTURE_RECOMMENDATION


def test_architecture_chat_task():
    client, _ = _make_mock_client("Azure App Service is recommended because it handles HTTPS and auto-scaling natively.")
    reply, prov = client.architecture_chat(
        message="Why App Service?",
        current_plan={"service": "App Service"},
    )
    assert "Azure App Service is recommended" in reply
    assert prov.task_type == TASK_ARCHITECTURE_CHAT


def test_analyze_failure_task():
    json_resp = json.dumps({
        "failure_summary": "Missing database URL",
        "root_cause": "KeyError: DATABASE_URL not in os.environ",
        "severity": "critical",
        "recommended_fix": "Add DATABASE_URL in App Service settings",
        "step_by_step_resolution": ["Go to Azure Portal", "Open Configuration", "Add DATABASE_URL"],
        "safe_to_auto_fix": False,
    })
    client, _ = _make_mock_client(json_resp)
    data, prov = client.analyze_failure(
        logs=["Error: KeyError: 'DATABASE_URL'"],
        build_logs="Build completed",
        stage="Container Run",
    )
    assert data["severity"] == "critical"
    assert data["recommended_fix"] == "Add DATABASE_URL in App Service settings"
    assert prov.task_type == TASK_FAILURE_ANALYSIS


def test_recommend_fix_task():
    json_resp = json.dumps({
        "recommended_fix": "Update Dockerfile to expose port 8000",
        "suggested_changes": [{"file": "Dockerfile", "description": "EXPOSE 8000", "action": "add"}],
        "step_by_step_resolution": ["Edit Dockerfile", "Rebuild image"],
    })
    client, _ = _make_mock_client(json_resp)
    data, prov = client.recommend_fix(
        failure_details={"error": "Port mismatch"},
        logs="Container failed to bind port",
    )
    assert len(data["suggested_changes"]) == 1
    assert prov.task_type == TASK_FIX_RECOMMENDATION


def test_analyze_security_task():
    json_resp = json.dumps({
        "summary": "1 high severity CVE detected in urllib3",
        "critical_issues": ["CVE-2023-45803 in urllib3"],
        "remediations": ["Upgrade urllib3 to >=2.0.7"],
        "should_block_deployment": True,
    })
    client, _ = _make_mock_client(json_resp)
    data, prov = client.analyze_security(
        scanner_findings={"trivy": ["CVE-2023-45803"]},
    )
    assert data["should_block_deployment"] is True
    assert prov.task_type == TASK_SECURITY_ANALYSIS


def test_generate_terraform_task():
    json_resp = json.dumps({
        "files": [
            {"path": "main.tf", "content": 'resource "azurerm_linux_web_app" "app" {}'},
            {"path": "versions.tf", "content": 'terraform { required_version = ">= 1.7" }'},
        ],
        "summary": "Generated Azure App Service plan and Linux Web App",
    })
    client, _ = _make_mock_client(json_resp)
    data, prov = client.generate_terraform(
        approved_plan={"service": "Azure App Service"},
    )
    assert len(data["files"]) == 2
    assert prov.task_type == TASK_TERRAFORM_GENERATION


def test_explain_pipeline_task():
    client, _ = _make_mock_client("Pipeline failed during Docker build stage due to missing dependencies.")
    explanation, prov = client.explain_pipeline(
        stages=[{"name": "Checkout", "status": "success"}, {"name": "Build", "status": "failed"}],
        current_stage="Build",
        status="failed",
    )
    assert "Pipeline failed" in explanation
    assert prov.task_type == TASK_PIPELINE_EXPLANATION


def test_optimize_cost_task():
    json_resp = json.dumps({
        "cost_summary": "Downsize App Service Plan from Standard S1 to Basic B1",
        "optimizations": [{"title": "Switch to B1", "service": "App Service", "proposed_change": "B1", "tradeoffs": "No autoscale slots"}],
        "estimated_savings_percentage": "50%",
    })
    client, _ = _make_mock_client(json_resp)
    data, prov = client.optimize_cost(
        current_plan={"service": "Azure App Service", "sku": "S1"},
    )
    assert data["estimated_savings_percentage"] == "50%"
    assert prov.task_type == TASK_COST_OPTIMIZATION


def test_guide_deployment_task():
    client, _ = _make_mock_client("Next step: Click 'Review & Approve Plan' to inspect the generated infrastructure specification before Terraform is created.")
    guidance, prov = client.guide_deployment(
        current_status="plan_generated",
        target="azure-app-service",
    )
    assert "Review & Approve Plan" in guidance
    assert prov.task_type == TASK_DEPLOYMENT_GUIDANCE


def test_authentication_error_401_handling():
    client, _ = _make_mock_client(status_code=401)
    with pytest.raises(FoundryAuthenticationError, match="401"):
        client.call_agent(task_type=TASK_ARCHITECTURE_CHAT, user_input="test")


def test_authorization_error_403_handling():
    client, _ = _make_mock_client(status_code=403)
    with pytest.raises(FoundryAuthorizationError, match="403"):
        client.call_agent(task_type=TASK_ARCHITECTURE_CHAT, user_input="test")


def test_empty_response_handling():
    client, _ = _make_mock_client(output_text="")
    with pytest.raises(FoundryAgentError, match="empty response"):
        client.call_agent(task_type=TASK_ARCHITECTURE_CHAT, user_input="test")


def test_singleton_accessor():
    client = ZeroOpsFoundryClient(
        endpoint="https://zeroops-aitest-resource.services.ai.azure.com/api/projects/zeroops-aitest",
        agent_name="demo",
        agent_version="1",
        openai_client=MagicMock(),
    )
    set_foundry_client(client)
    assert get_foundry_client() is client
    set_foundry_client(None)
