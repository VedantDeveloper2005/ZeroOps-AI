import json

from backend.services import ai


def test_local_node_analysis_does_not_invent_capacity_port_or_scores(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps(
            {
                "dependencies": {"next": "16.2.12"},
                "scripts": {"build": "next build"},
            }
        ),
        encoding="utf-8",
    )

    result = ai.analyze_repo_local(str(tmp_path), "truth-test")

    assert result["framework"] == "Next.js"
    assert result["build_commands"] == "npm run build"
    assert result["start_commands"] is None
    assert result["port"] is None
    assert result["resources"] == {"cpu": None, "memory": None, "storage": None}
    assert result["confidence"] == 0
    assert result["risk_score"] == 0
    assert result["dockerfile"] is None


def test_local_analysis_returns_only_repository_dockerfile(tmp_path):
    dockerfile = "FROM node:22-alpine\nEXPOSE 4321\n"
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {}, "scripts": {}}),
        encoding="utf-8",
    )
    (tmp_path / "Dockerfile").write_text(dockerfile, encoding="utf-8")

    result = ai.analyze_repo_local(str(tmp_path), "docker-truth-test")

    assert result["dockerfile"] == dockerfile
    assert result["port"] == "4321"
