from types import SimpleNamespace

try:
    from backend.services import decision_intelligence, planner
except ImportError:
    from services import decision_intelligence, planner


def _project():
    return SimpleNamespace(
        id="7e68a79e-af51-4f2c-89bd-4d3eae20dc19",
        name="customer-portal",
        framework="Next.js",
        language="TypeScript",
        region="eastus",
    )


def _facts():
    return {
        "framework": "Next.js",
        "runtime": "Node.js 22",
        "package_manager": "npm",
        "docker_support": True,
        "database_dependencies": [],
        "environment_variables": ["DATABASE_URL"],
        "vulnerabilities": [],
        "unresolved_questions": [],
    }


def test_knowledge_graph_links_evidence_without_accepting_secret_values():
    plan = planner.build_infrastructure_plan(_facts(), region="eastus")
    graph = decision_intelligence.build_knowledge_graph(
        project=_project(),
        analysis=_facts(),
        plan=plan,
        plan_revision=2,
    )

    serialized = str(graph)
    assert graph["plan_revision"] == 2
    assert any(node["type"] == "configuration_reference" for node in graph["nodes"])
    assert "DATABASE_URL" in serialized
    assert "super-secret-value" not in serialized
    assert all(node["properties"].get("value_present") is False for node in graph["nodes"] if node["type"] == "configuration_reference")


def test_digital_twin_blocks_execution_when_no_azure_target_is_ready():
    plan = planner.build_infrastructure_plan(_facts(), region="eastus")
    result = decision_intelligence.simulate_digital_twin(
        project=_project(),
        plan=plan,
        plan_revision=1,
        analysis=_facts(),
        target_status={"any_ready": False, "targets": []},
    )

    assert result["status"] == "blocked"
    assert result["risk_level"] in {"high", "critical"}
    target_check = next(check for check in result["checks"] if check["id"] == "azure-target")
    assert target_check["status"] == "blocked"
    assert target_check["risk_weight"] == 35


def test_digital_twin_makes_the_human_approval_gate_explicit():
    plan = planner.build_infrastructure_plan(_facts(), region="eastus")
    result = decision_intelligence.simulate_digital_twin(
        project=_project(),
        plan=plan,
        plan_revision=1,
        analysis=_facts(),
        target_status={"any_ready": True, "targets": [{"label": "Azure App Service"}]},
        plan_approved=True,
    )

    approval_check = next(check for check in result["checks"] if check["id"] == "human-approval")
    assert approval_check["status"] == "passed"
    assert result["status"] == "requires_review"  # Pricing evidence is intentionally still unknown.


def test_digital_twin_reports_unsupported_deployment_service_as_a_blocker():
    plan = planner.build_infrastructure_plan(_facts(), region="eastus")
    updated = planner.apply_plan_update(
        plan,
        region=None,
        component_id="application",
        service="Azure Container Apps",
        tier=None,
    )
    result = decision_intelligence.simulate_digital_twin(
        project=_project(),
        plan=updated,
        plan_revision=4,
        analysis=_facts(),
        target_status={"any_ready": True, "targets": [{"label": "Azure App Service"}]},
    )

    assert result["status"] == "blocked"
    assert any(check["id"] == "deployment-engine" and check["status"] == "blocked" for check in result["checks"])


def test_accuracy_uses_observed_terminal_outcomes_only():
    empty = decision_intelligence.decision_accuracy_summary([])
    result = decision_intelligence.decision_accuracy_summary([
        SimpleNamespace(status="successful"),
        SimpleNamespace(status="failed"),
        SimpleNamespace(status="pending"),
    ])

    assert empty["available"] is False
    assert empty["outcome_accuracy_percent"] is None
    assert result["available"] is True
    assert result["evaluated_deployments"] == 2
    assert result["pending_deployments"] == 1
    assert result["outcome_accuracy_percent"] == 50.0
