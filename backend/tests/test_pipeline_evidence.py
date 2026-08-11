from backend.services.pipeline_evidence import safe_analysis_summary


def test_safe_analysis_summary_drops_environment_values_and_source_material():
    result = safe_analysis_summary(
        {
            "framework": "FastAPI",
            "build_commands": "python -m compileall .",
            "environment_variables": [{"key": "API_TOKEN", "default_val": "secret"}],
            "dockerfile": "RUN echo secret",
            "resources": {"cpu": "1", "memory": "512Mi", "secret": "bad"},
        }
    )

    assert result["framework"] == "FastAPI"
    assert result["resources"] == {"cpu": "1", "memory": "512Mi"}
    assert "environment_variables" not in result
    assert "dockerfile" not in result
