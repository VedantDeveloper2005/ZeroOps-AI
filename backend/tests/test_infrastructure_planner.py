import json

import pytest

try:
    from backend import config
    from backend.services import planner, terraform_generator
except ImportError:
    import config
    from services import planner, terraform_generator


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


def test_chat_change_invalidates_deployable_target_without_hiding_limitation():
    plan = planner.build_infrastructure_plan(source_facts(), region="eastus")
    updated, summary = planner.apply_chat_instruction(plan, "Use Azure Container Apps")
    application = next(component for component in updated["components"] if component["id"] == "application")

    assert summary == "Application runtime changed to Azure Container Apps."
    assert application["service"] == "Azure Container Apps"
    assert application["deployable"] is False
    assert "currently deploys through Azure App Service only" in application["reason"]


def test_chat_can_switch_a_detected_database_to_cosmos():
    plan = planner.build_infrastructure_plan(source_facts(), region="eastus")
    updated, summary = planner.apply_chat_instruction(plan, "Can I use Cosmos DB instead?")
    database = next(component for component in updated["components"] if component["id"] == "database")

    assert summary == "Database changed to Azure Cosmos DB for MongoDB."
    assert database["service"] == "Azure Cosmos DB for MongoDB"


def test_region_updates_are_normalized_and_unknown_regions_are_rejected():
    plan = planner.build_infrastructure_plan(source_facts(), region="eastus")
    updated = planner.apply_plan_update(plan, region="West Europe", component_id=None, service=None, tier=None)

    assert updated["region_label"] == "West Europe"
    with pytest.raises(ValueError, match="supported Azure region"):
        planner.apply_plan_update(plan, region="Moon Base", component_id=None, service=None, tier=None)


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
