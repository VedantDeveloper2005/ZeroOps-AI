from __future__ import annotations

import json

import pytest

from backend.services.change_detection import (
    AnalysisDecisionReason,
    ChangeCategory,
    ChangeDetectionService,
    MAX_DETECTED_SERVICES,
    MAX_DETECTED_SERVICE_LENGTH,
    MAX_ENVIRONMENT_VARIABLE_NAMES,
    MAX_ENVIRONMENT_VARIABLE_NAME_LENGTH,
    MAX_SAMPLED_PATHS,
    build_change_analysis_persistence,
    classify_changes,
    classify_file,
    decide_analysis_reuse,
    fingerprint_repository,
    normalize_repository_path,
)


def _fingerprint(
    files: dict[str, str],
    *,
    sha: str,
    framework: str | None = "FastAPI",
    services: tuple[str, ...] = ("api",),
    environment_names: tuple[str, ...] = ("DATABASE_URL",),
):
    return fingerprint_repository(
        files,
        commit_sha=sha,
        application_framework=framework,
        detected_services=services,
        environment_variable_names=environment_names,
    )


def test_normalize_repository_path_is_cross_platform_and_rejects_unsafe_paths():
    assert normalize_repository_path(r".\src\api\main.py") == "src/api/main.py"

    for path in ("", "../secret", "/etc/passwd", r"C:\secret.txt", "a/../../secret"):
        with pytest.raises(ValueError):
            normalize_repository_path(path)


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("README.md", {ChangeCategory.NO_RELEVANT_CHANGE}),
        ("infra/README.md", {ChangeCategory.NO_RELEVANT_CHANGE}),
        ("src/orders.py", {ChangeCategory.APPLICATION_CODE_CHANGE}),
        ("package.json", {ChangeCategory.DEPENDENCY_CHANGE}),
        ("requirements-prod.txt", {ChangeCategory.DEPENDENCY_CHANGE}),
        ("Dockerfile.prod", {ChangeCategory.DEPLOYMENT_CONFIG_CHANGE}),
        (
            "docker-compose.yml",
            {
                ChangeCategory.DEPLOYMENT_CONFIG_CHANGE,
                ChangeCategory.MAJOR_ARCHITECTURE_CHANGE,
            },
        ),
        ("infra/main.tf", {ChangeCategory.INFRASTRUCTURE_CHANGE}),
        ("infra/main.tf.json", {ChangeCategory.INFRASTRUCTURE_CHANGE}),
        ("k8s/deployment.yaml", {ChangeCategory.KUBERNETES_CHANGE}),
        (
            "src/auth.py",
            {
                ChangeCategory.APPLICATION_CODE_CHANGE,
                ChangeCategory.SECURITY_RELEVANT_CHANGE,
            },
        ),
        (".github/workflows/deploy.yml", {ChangeCategory.DEPLOYMENT_CONFIG_CHANGE}),
        ("node_modules/pkg/index.js", {ChangeCategory.NO_RELEVANT_CHANGE}),
    ],
)
def test_classify_file_categories(path, expected):
    assert set(classify_file(path).categories) == expected


def test_classify_file_recognizes_kubernetes_yaml_by_bounded_content():
    result = classify_file(
        "ops/release.yaml",
        "apiVersion: apps/v1\nkind: Deployment\nmetadata:\n  name: api\n",
    )

    assert ChangeCategory.KUBERNETES_CHANGE in result.categories


def test_classify_changes_is_deduplicated_and_stably_ordered():
    first = classify_changes(["src/main.py", "README.md", "infra/main.tf", "src/main.py"])
    second = classify_changes(["infra/main.tf", "src/main.py", "README.md"])

    assert first == second
    assert first.primary_category is ChangeCategory.INFRASTRUCTURE_CHANGE
    assert first.categories == (
        ChangeCategory.INFRASTRUCTURE_CHANGE,
        ChangeCategory.APPLICATION_CODE_CHANGE,
    )
    assert [item.path for item in first.files] == ["README.md", "infra/main.tf", "src/main.py"]


def test_classify_changes_rejects_a_single_string_instead_of_iterating_characters():
    with pytest.raises(TypeError):
        classify_changes("src/main.py")


def test_fingerprint_is_independent_of_mapping_order_and_path_separators():
    first = _fingerprint(
        {"src/main.py": "print('ok')", "package.json": '{"name":"api"}'},
        sha="ABC123",
        services=("worker", "api", "api"),
        environment_names=("PORT", "DATABASE_URL", "PORT"),
    )
    second = _fingerprint(
        {"package.json": '{"name":"api"}', r"src\main.py": "print('ok')"},
        sha="abc123",
        services=("api", "worker"),
        environment_names=("DATABASE_URL", "PORT"),
    )

    assert first == second
    assert first.detected_services == ("api", "worker")
    assert first.environment_variable_names == ("DATABASE_URL", "PORT")
    assert set(first.to_dict()) >= {
        "commit_sha",
        "repository_fingerprint",
        "architecture_fingerprint",
        "dependency_files_hash",
        "dockerfile_hash",
        "infrastructure_files_hash",
        "kubernetes_manifests_hash",
        "important_configuration_files_hash",
    }


def test_documentation_changes_only_the_whole_repository_fingerprint():
    previous = _fingerprint(
        {"src/main.py": "print('ok')", "README.md": "old docs"},
        sha="a" * 40,
    )
    current = _fingerprint(
        {"src/main.py": "print('ok')", "README.md": "new docs"},
        sha="b" * 40,
    )

    assert previous.repository_fingerprint != current.repository_fingerprint
    assert previous.architecture_fingerprint == current.architecture_fingerprint
    assert previous.dependency_files_hash == current.dependency_files_hash
    assert previous.important_configuration_files_hash == current.important_configuration_files_hash


def test_environment_secret_values_never_influence_persisted_fingerprints():
    previous = _fingerprint(
        {"src/main.py": "same", ".env": "API_TOKEN=first-secret"},
        sha="1",
        environment_names=("API_TOKEN",),
    )
    rotated = _fingerprint(
        {"src/main.py": "same", ".env": "API_TOKEN=rotated-secret"},
        sha="2",
        environment_names=("API_TOKEN",),
    )
    renamed = _fingerprint(
        {"src/main.py": "same", ".env": "OTHER_TOKEN=rotated-secret"},
        sha="3",
        environment_names=("OTHER_TOKEN",),
    )

    assert previous.repository_fingerprint == rotated.repository_fingerprint
    assert previous.important_configuration_files_hash == rotated.important_configuration_files_hash
    assert previous.architecture_fingerprint == rotated.architecture_fingerprint
    assert previous.architecture_fingerprint != renamed.architecture_fingerprint


def test_group_hashes_change_only_for_the_relevant_file_family():
    previous = _fingerprint(
        {
            "src/main.py": "v1",
            "package.json": "deps-v1",
            "Dockerfile": "docker-v1",
            "infra/main.tf": "infra-v1",
            "k8s/deployment.yaml": "apiVersion: apps/v1\nkind: Deployment\nv1",
        },
        sha="1",
    )
    application_change = _fingerprint(
        {
            "src/main.py": "v2",
            "package.json": "deps-v1",
            "Dockerfile": "docker-v1",
            "infra/main.tf": "infra-v1",
            "k8s/deployment.yaml": "apiVersion: apps/v1\nkind: Deployment\nv1",
        },
        sha="2",
    )
    dependency_change = _fingerprint(
        {
            "src/main.py": "v1",
            "package.json": "deps-v2",
            "Dockerfile": "docker-v1",
            "infra/main.tf": "infra-v1",
            "k8s/deployment.yaml": "apiVersion: apps/v1\nkind: Deployment\nv1",
        },
        sha="3",
    )

    assert application_change.repository_fingerprint != previous.repository_fingerprint
    assert application_change.architecture_fingerprint == previous.architecture_fingerprint
    assert application_change.dependency_files_hash == previous.dependency_files_hash
    assert application_change.dockerfile_hash == previous.dockerfile_hash
    assert application_change.infrastructure_files_hash == previous.infrastructure_files_hash
    assert application_change.kubernetes_manifests_hash == previous.kubernetes_manifests_hash
    assert dependency_change.dependency_files_hash != previous.dependency_files_hash
    assert dependency_change.architecture_fingerprint != previous.architecture_fingerprint


def test_first_snapshot_requires_analysis():
    current = _fingerprint({"src/main.py": "v1"}, sha="1")

    decision = decide_analysis_reuse(previous=None, current=current, changed_files=["src/main.py"])

    assert decision.requires_repository_analysis is True
    assert decision.reuse_previous_analysis is False
    assert decision.reason is AnalysisDecisionReason.NO_PREVIOUS_ANALYSIS


@pytest.mark.parametrize("changed_file", ["README.md", "src/orders.py", "tests/test_orders.py"])
def test_documentation_and_application_changes_reuse_previous_analysis(changed_file):
    previous = _fingerprint({"src/orders.py": "v1"}, sha="1")
    current = _fingerprint({"src/orders.py": "v2"}, sha="2")

    decision = decide_analysis_reuse(
        previous=previous,
        current=current,
        changed_files=[changed_file],
    )

    assert decision.requires_repository_analysis is False
    assert decision.reuse_previous_analysis is True
    assert decision.reason is AnalysisDecisionReason.NO_DEPLOYMENT_RELEVANT_CHANGE
    assert decision.message == (
        "Repository AI analysis skipped because no deployment-relevant architecture "
        "changes were detected."
    )


@pytest.mark.parametrize(
    ("changed_file", "category"),
    [
        ("package.json", ChangeCategory.DEPENDENCY_CHANGE),
        ("Dockerfile", ChangeCategory.DEPLOYMENT_CONFIG_CHANGE),
        ("infra/main.tf", ChangeCategory.INFRASTRUCTURE_CHANGE),
        ("k8s/deployment.yaml", ChangeCategory.KUBERNETES_CHANGE),
        ("src/auth.py", ChangeCategory.SECURITY_RELEVANT_CHANGE),
        ("docker-compose.yml", ChangeCategory.MAJOR_ARCHITECTURE_CHANGE),
    ],
)
def test_deployment_relevant_path_requires_analysis(changed_file, category):
    previous = _fingerprint({"src/main.py": "v1"}, sha="1")
    current = _fingerprint({"src/main.py": "v2"}, sha="2")

    decision = decide_analysis_reuse(
        previous=previous,
        current=current,
        changed_files=[changed_file],
    )

    assert decision.requires_repository_analysis is True
    assert category in decision.categories
    assert category.value in decision.message


def test_fingerprint_delta_requires_analysis_without_a_changed_file_list():
    previous = _fingerprint({"package.json": "v1", "src/main.py": "same"}, sha="1")
    current = _fingerprint({"package.json": "v2", "src/main.py": "same"}, sha="2")

    decision = ChangeDetectionService.compare(previous=previous, current=current)

    assert decision.requires_repository_analysis is True
    assert decision.categories == (ChangeCategory.DEPENDENCY_CHANGE,)
    assert decision.changed_fingerprint_fields == (
        "repository_fingerprint",
        "architecture_fingerprint",
        "dependency_files_hash",
    )
    assert decision.changed_files == ()
    assert decision.to_dict()["reason"] == "deployment_relevant_change"


def test_analysis_metadata_changes_are_architecture_or_deployment_relevant():
    previous = _fingerprint(
        {"src/main.py": "same"},
        sha="1",
        framework="Flask",
        services=("api",),
        environment_names=("PORT",),
    )
    current = _fingerprint(
        {"src/main.py": "same"},
        sha="2",
        framework="FastAPI",
        services=("api", "worker"),
        environment_names=("DATABASE_URL", "PORT"),
    )

    decision = ChangeDetectionService.decide_analysis_reuse(previous=previous, current=current)

    assert decision.requires_repository_analysis is True
    assert ChangeCategory.MAJOR_ARCHITECTURE_CHANGE in decision.categories
    assert ChangeCategory.DEPLOYMENT_CONFIG_CHANGE in decision.categories
    assert decision.changed_fingerprint_fields == (
        "architecture_fingerprint",
        "application_framework",
        "detected_services",
        "environment_variable_names",
    )


def test_architecture_fingerprint_changes_for_deployment_metadata_but_not_application_source():
    baseline = _fingerprint(
        {"src/main.py": "v1", "Dockerfile": "FROM python:3.14"},
        sha="1",
    )
    application_change = _fingerprint(
        {"src/main.py": "v2", "Dockerfile": "FROM python:3.14"},
        sha="2",
    )
    docker_change = _fingerprint(
        {"src/main.py": "v2", "Dockerfile": "FROM python:3.15"},
        sha="3",
    )

    assert application_change.architecture_fingerprint == baseline.architecture_fingerprint
    assert docker_change.architecture_fingerprint != baseline.architecture_fingerprint


@pytest.mark.parametrize(
    ("argument", "maximum", "label"),
    [
        ("detected_services", MAX_DETECTED_SERVICES, "detected_services"),
        (
            "environment_variable_names",
            MAX_ENVIRONMENT_VARIABLE_NAMES,
            "environment_variable_names",
        ),
    ],
)
def test_persisted_name_evidence_fails_closed_when_count_exceeds_bound(
    argument,
    maximum,
    label,
):
    kwargs = {argument: (f"NAME_{index}" for index in range(maximum + 1))}

    with pytest.raises(ValueError, match=label):
        fingerprint_repository({}, commit_sha="1", **kwargs)


@pytest.mark.parametrize(
    ("argument", "maximum", "label"),
    [
        ("detected_services", MAX_DETECTED_SERVICE_LENGTH, "detected_services"),
        (
            "environment_variable_names",
            MAX_ENVIRONMENT_VARIABLE_NAME_LENGTH,
            "environment_variable_names",
        ),
    ],
)
def test_persisted_name_evidence_fails_closed_when_an_item_exceeds_bound(
    argument,
    maximum,
    label,
):
    kwargs = {argument: ("x" * (maximum + 1),)}

    with pytest.raises(ValueError, match=label):
        fingerprint_repository({}, commit_sha="1", **kwargs)


def test_change_analysis_persistence_is_bounded_deterministic_and_content_free():
    previous = _fingerprint({"src/main.py": "old"}, sha="1")
    current_files = {
        **{f"src/module_{index:03d}.py": f"secret-content-{index}" for index in range(125)},
        "package.json": "private-package-token-value",
    }
    current = _fingerprint(current_files, sha="2")

    first = build_change_analysis_persistence(
        previous=previous,
        current=current,
        changed_files=current_files,
    )
    second = build_change_analysis_persistence(
        previous=previous,
        current=current,
        changed_files=dict(reversed(tuple(current_files.items()))),
    )
    payload = first.to_dict()

    assert first == second
    assert first.changed_file_count == 126
    assert len(first.sampled_paths) == MAX_SAMPLED_PATHS
    assert first.sampled_paths == tuple(sorted(current_files))[:MAX_SAMPLED_PATHS]
    assert first.application_source_changed is True
    assert first.dependencies_changed is True
    assert first.deployment_relevant is True
    assert first.repository_ai_required is True
    assert first.documentation_only is False
    assert first.category_counts[ChangeCategory.APPLICATION_CODE_CHANGE.value] == 125
    assert first.category_counts[ChangeCategory.DEPENDENCY_CHANGE.value] == 1
    assert len(first.changed_paths_digest) == 64
    assert len(first.change_fingerprint) == 64
    assert payload["classifier_version"] == "change-detection-v1"
    assert isinstance(payload["sampled_paths"], list)
    serialized = json.dumps(payload)
    assert "secret-content" not in serialized
    assert "private-package-token-value" not in serialized


def test_documentation_only_persistence_reuses_analysis_with_visible_reason():
    previous = _fingerprint({"README.md": "old", "src/main.py": "same"}, sha="1")
    current = _fingerprint({"README.md": "new", "src/main.py": "same"}, sha="2")

    persisted = ChangeDetectionService.build_change_analysis_persistence(
        previous=previous,
        current=current,
        changed_files=["README.md"],
    )

    assert persisted.documentation_only is True
    assert persisted.deployment_relevant is False
    assert persisted.repository_ai_required is False
    assert persisted.category_counts[ChangeCategory.NO_RELEVANT_CHANGE.value] == 1
    assert persisted.decision_reason == (
        "Repository AI analysis skipped because no deployment-relevant architecture "
        "changes were detected."
    )


def test_first_change_analysis_requires_ai_without_claiming_a_relevant_diff():
    current = _fingerprint({"src/main.py": "same"}, sha="1")

    persisted = build_change_analysis_persistence(
        previous=None,
        current=current,
        changed_files=(),
    )

    assert persisted.changed_file_count == 0
    assert persisted.documentation_only is False
    assert persisted.deployment_relevant is False
    assert persisted.repository_ai_required is True
