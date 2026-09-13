import sys
from pathlib import Path
from types import SimpleNamespace

import pytest
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "common"))
from zeroops_functions.model_client import StructuredModelClient, ModelContractError


class Answer(BaseModel):
    result: str


def client(**overrides):
    settings = dict(provider="azure-foundry", endpoint="https://account.services.ai.azure.com/api/projects/zeroops",
                    model="gpt-5.6-terra", api_key="ignored-old-key", credential=object(),
                    workload="terraform-generation", prompt_version="terraform-generation.v1",
                    maximum_input_chars=20000, maximum_output_tokens=4000)
    return StructuredModelClient(**(settings | overrides))


def install_agent(monkeypatch, status="completed"):
    import azure.ai.projects
    calls = {}

    class Project:
        def __init__(self, **kwargs):
            calls["project"] = kwargs

        def __enter__(self):
            return self

        def __exit__(self, *_):
            pass

        def get_openai_client(self, **kwargs):
            calls["client"] = kwargs
            return self

        @property
        def responses(self):
            return self

        def create(self, **kwargs):
            calls["request"] = kwargs
            return SimpleNamespace(status=status, output_text='{"result":"real output"}',
                                   usage=SimpleNamespace(input_tokens=15, output_tokens=6))

    monkeypatch.setattr(azure.ai.projects, "AIProjectClient", Project)
    return calls


def test_agent_route_uses_identity_bound_client_and_preserves_provenance(monkeypatch):
    calls = install_agent(monkeypatch)
    route = client()
    answer, provenance = route.generate(system_instructions="Generate an approved Terraform proposal.",
        input_value={"plan_revision": 1}, output_model=Answer, schema_version="test.v1")
    assert answer.result == "real output"
    assert route.api_key == ""
    assert calls["project"]["allow_preview"] is True
    assert calls["project"]["credential"] is route.credential
    assert calls["client"]["agent_name"] == "zeroops-architecture-advisor"
    assert calls["request"]["extra_body"]["agent_reference"]["version"] == "3"
    assert "TERRAFORM_GENERATION" in calls["request"]["input"][0]["content"]
    assert calls["request"]["store"] is False
    assert provenance.execution_mode == "model"
    assert (provenance.input_tokens, provenance.output_tokens) == (15, 6)


@pytest.mark.parametrize("status", ["incomplete", "failed", "cancelled"])
def test_incomplete_agent_output_is_not_accepted(monkeypatch, status):
    install_agent(monkeypatch, status)
    with pytest.raises(ModelContractError):
        client().generate(system_instructions="Generate.", input_value={}, output_model=Answer, schema_version="test.v1")


@pytest.mark.parametrize("endpoint", ["http://account.services.ai.azure.com/api/projects/a",
    "https://evil.example/api/projects/a", "https://account.services.ai.azure.com/api/projects/a?key=secret"])
def test_agent_endpoint_validation(endpoint):
    with pytest.raises(ValueError):
        client(endpoint=endpoint)
