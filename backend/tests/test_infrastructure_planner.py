import json
from datetime import datetime
from types import SimpleNamespace

import pytest

try:
    from backend import config
    from backend.services import deployment_targets, planner, terraform_generator
except ImportError:
    import config
    from services import deployment_targets, planner, terraform_generator


def source_facts():
    return {
        "framework": "Next.js",
        "runtime": "Node.js 22",
        "package_manager": "npm",
        "docker_support": True,
        "database_dependencies": ["PostgreSQL", "Redis"],
        "environment_variables": ["DATABASE_URL", "NEXTAUTH_SECRET"],
        "vulnerabilities": [],
        "unresolved_questions": ["Which retention period applies to customer data?"],
    }


def test_plan_uses_source_evidence_without_inventing_pricing_or_secrets():
    plan = planner.build_infrastructure_plan(source_facts(), region="centralindia")
    components = {component["id"]: component for component in plan["components"]}

    assert components["application"]["service"] == "Azure App Service"
    assert components["database"]["service"] == "Azure Database for PostgreSQL Flexible Server"
    assert components["cache"]["service"] == "Azure Cache for Redis"
    assert components["secrets"]["service"] == "Azure Key Vault"
    assert plan["cost"]["monthly_estimate"] is None
    assert plan["cost"]["status"] == "requires_connected_azure_subscription"
    serialized = json.dumps(plan)
    assert "NEXTAUTH_SECRET" in serialized  # names guide setup; values are never collected.
    assert "terraform" not in serialized.lower()


def test_plan_does_not_claim_an_unverified_azure_target_is_verified():
    unverified = SimpleNamespace(app_service_plan="legacy-plan")

    plan = planner.build_infrastructure_plan(
        source_facts(),
        region="eastus",
        azure_connection=unverified,
    )
    application = next(
        component for component in plan["components"] if component["id"] == "application"
    )

    assert application["tier"] == "Existing Linux App Service plan required"
    assert "after an Azure deployment target is connected and verified" in application["reason"]
    assert "is the verified deployment target" not in application["reason"]


def test_plan_reports_only_a_fingerprint_bound_target_as_verified():
    connection = SimpleNamespace(
        tenant_id="tenant",
        subscription_id="subscription",
        client_id="client",
        region="eastus",
        resource_group="apps-rg",
        acr_login_server="appsregistry.azurecr.io",
        app_service_plan="verified-linux-plan",
        connection_status="connected",
        is_active=True,
        deployment_target_verified_at=datetime(2026, 1, 1),
        deployment_target_fingerprint=None,
    )
    connection.deployment_target_fingerprint = deployment_targets.configuration_fingerprint(
        connection
    )

    plan = planner.build_infrastructure_plan(
        source_facts(),
        region="eastus",
        azure_connection=connection,
    )
    application = next(
        component for component in plan["components"] if component["id"] == "application"
    )

    assert application["tier"] == "verified-linux-plan"
    assert "is the verified deployment target" in application["reason"]


def test_detailed_spec_and_revisions_do_not_invent_costs_or_readiness_scores():
    specification = planner.build_infrastructure_spec(source_facts(), region="eastus")

    assert specification["cost"]["monthly_estimate"] is None
    assert specification["cost"]["status"] == "requires_connected_azure_subscription"
    assert specification["assessment"]["security"]["value"] is None
    assert specification["assessment"]["performance"]["value"] is None
    assert specification["assessment"]["reliability"]["value"] is None
    assert specification["deployment_time"]["estimate"] is None

    updated = planner.apply_plan_update(
        specification,
        region=None,
        component_id="application",
        service=None,
        tier="P0v3",
    )
    assert updated["cost"]["monthly_estimate"] is None
    assert updated["assessment"]["security"]["value"] is None


def test_chat_change_invalidates_deployable_target_without_hiding_limitation():
    plan = planner.build_infrastructure_plan(source_facts(), region="eastus")
    updated, summary = planner.apply_chat_instruction(plan, "Use Azure Container Apps")
    application = next(component for component in updated["components"] if component["id"] == "application")

    assert summary == "Application runtime changed to Azure Container Apps."
    assert application["service"] == "Azure Container Apps"
    assert application["deployable"] is False
    assert "currently deploys through Azure App Service only" in application["reason"]


def test_chat_questions_are_read_only_even_when_they_name_a_service():
    plan = planner.build_infrastructure_plan(source_facts(), region="eastus")
    updated, summary = planner.apply_chat_instruction(plan, "Can I use Cosmos DB instead?")
    database = next(component for component in updated["components"] if component["id"] == "database")

    assert summary is None
    assert updated == plan
    assert database["service"] == "Azure Database for PostgreSQL Flexible Server"


def test_chat_explicit_command_can_switch_a_detected_database_to_cosmos():
    plan = planner.build_infrastructure_plan(source_facts(), region="eastus")
    updated, summary = planner.apply_chat_instruction(plan, "Use Cosmos DB instead")
    database = next(component for component in updated["components"] if component["id"] == "database")

    assert summary == "Database changed to Azure Cosmos DB for MongoDB."
    assert database["service"] == "Azure Cosmos DB for MongoDB"


def test_architect_question_explains_the_saved_plan_without_mutating_it(monkeypatch):
    plan = planner.build_infrastructure_plan(source_facts(), region="eastus")
    monkeypatch.setattr("backend.services.ai.GITHUB_MODELS_API_KEY", "")
    monkeypatch.setattr("backend.services.ai.OPENAI_API_KEY", "")

    try:
        from backend.services import ai
    except ImportError:
        from services import ai

    updated, reply = ai.architect_chat("Why App Service?", plan)

    assert updated == plan
    assert "connected and verified" in reply
    assert "not proof of live Azure readiness" in reply
    assert "Plan updated" not in reply


def test_architect_combined_detection_validation_question_uses_saved_evidence_without_mutation(monkeypatch):
    plan = planner.build_infrastructure_plan(source_facts(), region="eastus")
    monkeypatch.setattr("backend.services.ai.GITHUB_MODELS_API_KEY", "")
    monkeypatch.setattr("backend.services.ai.OPENAI_API_KEY", "")

    try:
        from backend.services import ai
    except ImportError:
        from services import ai

    updated, reply = ai.architect_chat(
        "What framework was detected, and what still needs validation before deployment?",
        plan,
    )

    assert updated == plan
    assert "**Next.js**" in reply
    assert "runtime: Node.js 22" in reply
    assert "Connect and validate an Azure environment" in reply
    assert "Security: requires configuration review" in reply
    assert "Which retention period applies to customer data?" in reply
    assert "Plan updated" not in reply
    assert "Ask about a recorded decision" not in reply


def test_architect_combined_detection_validation_question_does_not_invent_missing_evidence(monkeypatch):
    monkeypatch.setattr("backend.services.ai.GITHUB_MODELS_API_KEY", "")
    monkeypatch.setattr("backend.services.ai.OPENAI_API_KEY", "")

    try:
        from backend.services import ai
    except ImportError:
        from services import ai

    plan = {"components": [], "assessment": {}}
    updated, reply = ai.architect_chat(
        "What framework was detected and what needs validation before deployment?",
        plan,
    )

    assert updated == plan
    assert "did not record one" in reply
    assert "absence is not proof of deployment readiness" in reply
    assert "Next.js" not in reply
    assert "Plan updated" not in reply


def test_architect_explicit_edit_preserves_the_requested_service(monkeypatch):
    try:
        from backend.services import ai
    except ImportError:
        from services import ai

    plan = planner.build_infrastructure_plan(source_facts(), region="eastus")
    updated, reply = ai.architect_chat("Use Azure Container Apps", plan)
    application = next(component for component in updated["components"] if component["id"] == "application")

    assert application["service"] == "Azure Container Apps"
    assert application["deployable"] is False
    assert "Plan updated" in reply


def test_region_updates_are_normalized_and_unknown_regions_are_rejected():
    plan = planner.build_infrastructure_plan(source_facts(), region="eastus")
    updated = planner.apply_plan_update(plan, region="West Europe", component_id=None, service=None, tier=None)

    assert updated["region_label"] == "West Europe"
    with pytest.raises(ValueError, match="supported Azure region"):
        planner.apply_plan_update(plan, region="Moon Base", component_id=None, service=None, tier=None)


def test_chat_capacity_commands_keep_tiers_compatible_with_selected_services():
    plan = planner.build_infrastructure_plan(source_facts(), region="eastus")
    plan, _ = planner.apply_chat_instruction(plan, "Use Azure Container Apps")
    plan, _ = planner.apply_chat_instruction(plan, "Use Cosmos DB instead")

    scaled, scale_summary = planner.apply_chat_instruction(plan, "Scale up")
    scaled_components = {component["id"]: component for component in scaled["components"]}
    assert scale_summary is not None
    assert scaled_components["application"]["tier"] == "Dedicated"
    assert scaled_components["database"]["tier"] == "Configuration required"

    reduced, cost_summary = planner.apply_chat_instruction(scaled, "Reduce cost")
    reduced_components = {component["id"]: component for component in reduced["components"]}
    assert cost_summary is not None
    assert reduced_components["application"]["tier"] == "Consumption"
    assert reduced_components["database"]["tier"] == "Configuration required"


def test_internal_iac_artifact_exposes_metadata_only(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "WORKSPACE_DIR", str(tmp_path))
    plan = planner.build_infrastructure_plan(source_facts(), region="eastus")
    plan["revision"] = 3

    metadata = terraform_generator.generate_internal_artifact(
        plan=plan,
        project_id="9d75d9fc-2dd6-4e0a-95ce-2d34e8d4efaa",
        project_name="customer-portal",
    )

    assert metadata["engine"] == "terraform"
    assert metadata["status"] == "generated"
    assert metadata["plan_revision"] == 3
    assert "artifact_path" not in metadata
    assert "azurerm_linux_web_app" in metadata["resource_kinds"]
    assert len(metadata["artifact_sha256"]) == 64
    artifact = (tmp_path / "internal-iac" / "9d75d9fc-2dd6-4e0a-95ce-2d34e8d4efaa" / "main.tf").read_text(encoding="utf-8")
    assert "DATABASE_URL" not in artifact
    assert "NEXTAUTH_SECRET" not in artifact
