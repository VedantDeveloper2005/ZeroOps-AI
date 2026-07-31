import json
from pathlib import Path
from uuid import UUID

import pytest
from pydantic import ValidationError

from backend.contracts.ai import (
    RepositoryAnalysisRequest,
    RepositoryAssessment,
    TerraformBundle,
)


SPEC_ROOT = Path(__file__).resolve().parents[2] / "ai-specs"


def _read_json(relative_path: str) -> dict:
    return json.loads((SPEC_ROOT / relative_path).read_text(encoding="utf-8"))


def test_generated_runtime_schemas_match_canonical_contracts_exactly():
    pairs = [
        ("repository-analysis/response.schema.json", RepositoryAssessment),
        ("terraform-generation/response.schema.json", TerraformBundle),
    ]
    for relative_path, contract in pairs:
        checked_in_schema = _read_json(relative_path)
        runtime_schema = contract.model_json_schema()
        assert checked_in_schema == runtime_schema


def test_foundry_schemas_use_only_supported_structural_subset():
    unsupported = {
        "$defs",
        "$ref",
        "$schema",
        "default",
        "format",
        "maxItems",
        "maxLength",
        "maximum",
        "minItems",
        "minLength",
        "minimum",
        "pattern",
        "uniqueItems",
    }

    def walk(value, *, property_map=False):
        if isinstance(value, dict):
            if property_map:
                for item in value.values():
                    walk(item)
                return

            assert not (set(value) & unsupported)
            if value.get("type") == "object":
                assert value.get("additionalProperties") is False
                assert set(value.get("required", [])) == set(
                    value.get("properties", {})
                )
            for key, item in value.items():
                walk(item, property_map=key == "properties")
        elif isinstance(value, list):
            for item in value:
                walk(item)

    for relative_path in [
        "repository-analysis/response.foundry.schema.json",
        "terraform-generation/response.foundry.schema.json",
    ]:
        walk(_read_json(relative_path))


def test_evaluation_datasets_are_valid_jsonl_and_contain_regression_coverage():
    for relative_path in [
        "repository-analysis/evaluation.dataset.jsonl",
        "terraform-generation/evaluation.dataset.jsonl",
    ]:
        lines = [
            line
            for line in (SPEC_ROOT / relative_path).read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        records = [json.loads(line) for line in lines]
        tags = {tag for record in records for tag in record["tags"]}

        assert len(records) >= 5
        assert all(record["query"] and record["expected_behavior"] for record in records)
        assert "prompt-injection" in tags
        assert "cost" in tags


def test_specs_use_current_github_model_conventions_and_foundry_isolation():
    repository_prompt = (
        SPEC_ROOT / "repository-analysis/github-models.prompt.yml"
    ).read_text(encoding="utf-8")
    terraform_prompt = (
        SPEC_ROOT / "terraform-generation/github-models.prompt.yml"
    ).read_text(encoding="utf-8")
    portal_guide = (SPEC_ROOT / "FOUNDRY-PORTAL.md").read_text(encoding="utf-8")

    assert "model: openai/gpt-4o" in repository_prompt
    assert "model: openai/gpt-4.1" in terraform_prompt
    assert "temperature: 0" in repository_prompt
    assert "temperature: 0" in terraform_prompt
    assert "https://models.github.ai/inference" in portal_guide
    assert "zeroops-repository-analyst" in portal_guide
    assert "zeroops-terraform-generator" in portal_guide
    assert "managed identity" in portal_guide.lower()
    assert "must not be able to read" in " ".join(portal_guide.lower().split())


def test_instruction_files_preserve_truth_security_cost_and_execution_boundaries():
    repository = (SPEC_ROOT / "repository-analysis/instructions.md").read_text(
        encoding="utf-8"
    ).lower()
    terraform = (SPEC_ROOT / "terraform-generation/instructions.md").read_text(
        encoding="utf-8"
    ).lower()

    for phrase in [
        "untrusted data",
        "never follow instructions",
        "do not invent numerical azure prices",
        "hidden chain-of-thought",
        "evidence",
    ]:
        assert phrase in repository

    for phrase in [
        "untrusted data",
        "plan_status",
        "never generate provisioners",
        "human approval before apply",
        "verified pricing",
        "hidden chain-of-thought",
    ]:
        assert phrase in terraform


def test_repository_contract_rejects_sensitive_context_and_unverified_cost_amounts():
    with pytest.raises(ValidationError, match="sensitive or unsafe path"):
        RepositoryAnalysisRequest.model_validate(
            {
                "schema_version": "repository-analysis-request.v1",
                "tenant_id": UUID("11111111-1111-1111-1111-111111111111"),
                "project_id": UUID("22222222-2222-2222-2222-222222222222"),
                "repository": "owner/repository",
                "branch": "main",
                "commit_sha": "a" * 40,
                "source_facts": [],
                "safe_files": [
                    {
                        "id": "unsafe-env",
                        "path": ".env",
                        "content": "A_VALUE=<not-model-context>",
                        "sha256": "b" * 64,
                        "truncated": False,
                    }
                ],
                "repository_tree": "",
                "constraints": [],
            }
        )

    with pytest.raises(ValidationError, match="names only"):
        RepositoryAnalysisRequest.model_validate(
            {
                "schema_version": "repository-analysis-request.v1",
                "tenant_id": UUID("11111111-1111-1111-1111-111111111111"),
                "project_id": UUID("22222222-2222-2222-2222-222222222222"),
                "repository": "owner/repository",
                "branch": "main",
                "commit_sha": "a" * 40,
                "source_facts": [
                    {
                        "id": "env-database",
                        "category": "environment-variable",
                        "value": "DATABASE_URL=not-allowed",
                        "source_path": "app.py",
                        "source_line": 1,
                    }
                ],
                "safe_files": [],
                "repository_tree": "",
                "constraints": [],
            }
        )

    with pytest.raises(ValidationError, match="numerical cost"):
        RepositoryAssessment.model_validate(
            {
                "schema_version": "repository-assessment.v1",
                "summary": "Bounded summary.",
                "deployment_risk": "Unknown traffic.",
                "recommendations": [],
                "cost_optimizations": [
                    {
                        "id": "invented-price",
                        "title": "Invented price",
                        "rationale": "This will cost $10 without a pricing source.",
                        "evidence_refs": ["fact-1"],
                        "expected_impact": "unknown",
                        "tradeoffs": [],
                        "validation_needed": "Check the subscription price.",
                    }
                ],
                "unresolved_questions": [],
                "confidence": "low",
                "limitations": [],
            }
        )


def test_spec_assets_do_not_contain_secret_values():
    suspicious_value_patterns = (
        "ghp_",
        "github_pat_",
        "sk-proj-",
        "-----begin private key-----",
        "accountkey=",
    )
    for path in SPEC_ROOT.rglob("*"):
        if not path.is_file():
            continue
        content = path.read_text(encoding="utf-8").lower()
        assert not any(pattern in content for pattern in suspicious_value_patterns), path
