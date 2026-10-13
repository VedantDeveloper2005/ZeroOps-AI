"""Tests for customer-scoped ARM provisioning, TTL cleanup, and integrations."""

import json
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from backend import models, schemas
from backend.services import ephemeral_resources, resource_chat
from backend.services.ephemeral_resources import (
    RESOURCE_CATALOG,
    REGIONS,
    destroy_ephemeral_resource,
    provision_ephemeral_resource,
    reap_expired_ephemeral_resources,
    validate_custom_arm_template,
)
from backend.services.resource_chat import parse_intent_rule_based, process_resource_chat
from backend.services.jira_service import process_jira_webhook, format_jira_provision_comment
from backend.services.inbound_email_service import process_inbound_developer_email
from backend.services.deployment_targets import configuration_fingerprint


def arm_template(name="zoteststorage123", resource_type="Microsoft.Storage/storageAccounts"):
    return {
        "$schema": "https://schema.management.azure.com/schemas/2019-04-01/deploymentTemplate.json#",
        "contentVersion": "1.0.0.0",
        "resources": [{
            "type": resource_type,
            "apiVersion": "2023-05-01",
            "name": name,
            "location": "eastus",
            "sku": {"name": "Standard_LRS"},
            "kind": "StorageV2",
            "tags": {},
            "properties": {"accessTier": "Hot"},
        }],
    }


class NotFoundError(Exception):
    status_code = 404


class FakePoller:
    def __init__(self, result=None):
        self.value = result

    def result(self):
        return self.value


class FakeAzureResourceClient:
    def __init__(self):
        self.deployed = []
        self.deleted = []
        self.deleted_deployments = []
        self.resources = SimpleNamespace(
            get_by_id=self.get_by_id,
            begin_delete_by_id=self.begin_delete_by_id,
        )
        self.deployments = SimpleNamespace(
            begin_create_or_update=self.begin_create_or_update,
            begin_delete=self.begin_delete,
        )

    def get_by_id(self, resource_id, *, api_version):
        raise NotFoundError()

    def begin_create_or_update(self, group, deployment_name, payload):
        self.deployed.append((group, deployment_name, payload))
        result = SimpleNamespace(properties=SimpleNamespace(provisioning_state="Succeeded"))
        return FakePoller(result)

    def begin_delete_by_id(self, resource_id, *, api_version):
        self.deleted.append((resource_id, api_version))
        return FakePoller()

    def begin_delete(self, group, deployment_name):
        self.deleted_deployments.append((group, deployment_name))
        return FakePoller()


@pytest_asyncio.fixture
async def in_memory_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        user = models.User(
            id=uuid.uuid4(), email="developer@company.com", first_name="Alice", last_name="Tester"
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        yield session, user
    await engine.dispose()


async def connect_azure(session, user):
    connection = models.UserAzureConnection(
        user_id=user.id,
        tenant_id="tenant-1",
        subscription_id="subscription-1",
        client_id="client-1",
        connection_status="connected",
        resource_group="zeroops-test-rg",
        region="eastus",
        is_active=True,
        deployment_target_verified_at=datetime.now(timezone.utc),
    )
    connection.deployment_target_fingerprint = configuration_fingerprint(connection)
    session.add(connection)
    await session.commit()
    client = FakeAzureResourceClient()
    async def get_clients(user_id, db, connection_id=None):
        assert user_id == user.id
        assert connection_id == connection.id
        return {
            "resource": client,
            "resource_group": "zeroops-test-rg",
            "subscription_id": "subscription-1",
        }
    ephemeral_resources.azure_connector.get_azure_clients_async = get_clients
    return client


def create_request(**overrides):
    values = {
        "name": "custom-storage-test",
        "resource_type": "custom_arm",
        "region": "eastus",
        "sku": "Standard_LRS",
        "ttl_minutes": 120,
        "arm_template": arm_template(),
        "arm_parameters": {},
        "estimated_resource_hourly_usd": 0.12,
    }
    values.update(overrides)
    return schemas.EphemeralResourceCreateRequest(**values)


def test_resource_catalog_exposes_real_custom_deployment_path():
    assert list(RESOURCE_CATALOG) == ["custom_arm"]
    assert len(REGIONS) >= 5
    assert any(region["id"] == "eastus" for region in REGIONS)


def test_arm_validation_stamps_tags_and_rejects_cross_scope_or_secrets():
    normalized, manifest = validate_custom_arm_template(arm_template(), "eastus", "resource-123")
    resource = normalized["resources"][0]
    assert resource["location"] == "eastus"
    assert resource["tags"]["zeroops-managed"] == "true"
    assert resource["tags"]["zeroops-resource-id"] == "resource-123"
    assert manifest[0]["id_suffix"].endswith("storageAccounts/zoteststorage123")

    cross_scope = arm_template()
    cross_scope["resources"][0]["scope"] = "/subscriptions/other"
    with pytest.raises(ValueError, match="scope"):
        validate_custom_arm_template(cross_scope, "eastus", "resource-123")

    embedded_secret = arm_template()
    embedded_secret["variables"] = {"someValue": {"clientSecret": "literal-secret"}}
    with pytest.raises(ValueError, match="Sensitive ARM value"):
        validate_custom_arm_template(embedded_secret, "eastus", "resource-123")


def test_lifecycle_intent_parser_handles_controls():
    assert parse_intent_rule_based("Extend my VM by 1 hour")["action"] == "extend_ttl"
    assert parse_intent_rule_based("Destroy the sandbox now")["action"] == "destroy_resource"
    assert parse_intent_rule_based("What sandboxes are currently running?")["action"] == "query_status"


@pytest.mark.asyncio
async def test_chat_requires_price_and_prepares_reviewable_template(monkeypatch, in_memory_db):
    _, user = in_memory_db
    missing_price = await process_resource_chat("I need Azure storage in East US for 2 hours", user)
    assert missing_price.action_detected == "needs_details"
    assert missing_price.proposed_resource is None

    generated = {"name": "storage-for-tests", "sku": "Standard_LRS", "arm_template": arm_template()}
    monkeypatch.setattr(resource_chat, "generate_chat_response", lambda *_args, **_kwargs: json.dumps(generated))
    plan = await process_resource_chat(
        "Create a storage account in East US for 2 hours, Azure estimate $0.12/hr", user,
        selected_region="centralindia",
    )
    assert plan.action_detected == "propose_resource"
    assert plan.proposed_resource.resource_type == "custom_arm"
    assert plan.proposed_resource.region == "centralindia"
    assert plan.proposed_resource.arm_template["resources"][0]["location"] == "centralindia"
    assert plan.proposed_resource.hourly_subtotal == 0.146
    assert plan.proposed_resource.total_subtotal == 0.292
    assert "subtotal" in plan.reply.lower()
    assert "platform fee" not in plan.reply.lower()
    assert "ai fee" not in plan.reply.lower()


@pytest.mark.asyncio
async def test_real_arm_lifecycle_and_exact_teardown(in_memory_db):
    session, user = in_memory_db
    azure_client = await connect_azure(session, user)

    resource = await provision_ephemeral_resource(session, user, create_request())
    assert resource.status == "active"
    assert resource.azure_resource_group == "zeroops-test-rg"
    assert len(azure_client.deployed) == 1
    assert resource.connection_info["portal_url"].startswith("https://portal.azure.com/")
    assert resource.configuration["resource_count"] == 1
    assert "estimated_resource_hourly_usd" not in resource.configuration
    assert resource.cost_estimate_hourly == 0.146

    expires = resource.expires_at.replace(tzinfo=timezone.utc) if resource.expires_at.tzinfo is None else resource.expires_at
    assert expires > datetime.now(timezone.utc)
    extended = await ephemeral_resources.extend_ephemeral_resource(session, user.id, resource.id, 60)
    assert extended.ttl_minutes == 180

    deleted = await destroy_ephemeral_resource(session, extended, reason="Test teardown")
    assert deleted.status == "destroyed"
    assert len(azure_client.deleted) == 1
    assert azure_client.deleted[0][0] == resource.azure_resource_id
    assert len(azure_client.deleted_deployments) == 1


@pytest.mark.asyncio
async def test_provision_requires_verified_connection_and_only_activates_on_azure_success(in_memory_db):
    session, user = in_memory_db
    with pytest.raises(ephemeral_resources.AzureResourceProvisioningError, match="Connect and verify"):
        await provision_ephemeral_resource(session, user, create_request())

    azure_client = await connect_azure(session, user)
    azure_client.deployments.begin_create_or_update = lambda *_args: FakePoller(
        SimpleNamespace(properties=SimpleNamespace(provisioning_state="Failed"))
    )
    with pytest.raises(ephemeral_resources.AzureResourceProvisioningError, match="did not confirm"):
        await provision_ephemeral_resource(session, user, create_request(name="failed-resource"))
    rows = (await session.execute(
        __import__("sqlalchemy").select(models.EphemeralResource)
    )).scalars().all()
    assert rows
    assert all(row.status != "active" for row in rows)
    assert azure_client.deleted


@pytest.mark.asyncio
async def test_auto_destroy_reaper_deletes_expired_azure_resources(in_memory_db):
    session, user = in_memory_db
    azure_client = await connect_azure(session, user)
    resource = await provision_ephemeral_resource(session, user, create_request())
    resource.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    await session.commit()

    assert await reap_expired_ephemeral_resources(session) == 1
    await session.refresh(resource)
    assert resource.status == "destroyed"
    assert len(azure_client.deleted) == 1


@pytest.mark.asyncio
async def test_legacy_untracked_rows_never_claim_live_cost_or_successful_deletion(in_memory_db):
    session, user = in_memory_db
    legacy = models.EphemeralResource(
        id=uuid.uuid4(),
        user_id=user.id,
        name="old-demo-vm",
        resource_type="vm_linux",
        region="eastus",
        sku="Standard_B2s",
        status="active",
        source="catalog_ui",
        ttl_minutes=120,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        cost_estimate_hourly=9.99,
        connection_info={"public_ip": "203.0.113.99"},
        configuration={},
        logs=[{"message": "old simulated connection details"}],
    )
    session.add(legacy)
    await session.commit()
    await session.refresh(legacy)

    from backend.routes.ephemeral_resources import _serialize_resource
    serialized = _serialize_resource(legacy)
    assert serialized.status == "unverified"
    assert serialized.cost_estimate_hourly == 0
    assert serialized.connection_info == {}
    assert "unverified" in serialized.logs[0]["message"].lower()
    with pytest.raises(ValueError, match="cannot be extended"):
        await ephemeral_resources.extend_ephemeral_resource(session, user.id, legacy.id, 60)

    result = await destroy_ephemeral_resource(session, legacy)
    assert result.status == "unverified"
    assert result.destroyed_at is None
    assert "could not confirm" in result.logs[-1]["message"].lower()


@pytest.mark.asyncio
async def test_jira_webhook_is_project_scoped_and_provisions_then_tears_down(monkeypatch, in_memory_db):
    session, user = in_memory_db
    azure_client = await connect_azure(session, user)
    integration = models.IntegrationConfig(
        user_id=user.id,
        jira_enabled=True,
        jira_project_keys=["QA"],
        jira_auto_provision=True,
    )
    session.add(integration)
    await session.commit()
    generated = {"name": "jira-storage", "sku": "Standard_LRS", "arm_template": arm_template("zotestjira123")}
    monkeypatch.setattr(resource_chat, "generate_chat_response", lambda *_args, **_kwargs: json.dumps(generated))
    from backend.services import jira_service
    monkeypatch.setattr(jira_service, "_post_jira_comment", AsyncMock(return_value=True))

    rejected = await process_jira_webhook(session, {"issue": {"key": "OPS-1", "fields": {}}}, user.id)
    assert rejected["status"] == "ignored"

    payload = {
        "webhookEvent": "jira:issue_created",
        "issue": {"key": "QA-701", "fields": {
            "summary": "Need Azure storage for tests",
            "description": "Create a storage account in East US for 3 hours. Azure estimate $0.12/hr.",
            "labels": ["zeroops-sandbox"],
            "status": {"name": "In Progress"},
        }},
    }
    result = await process_jira_webhook(session, payload, user.id)
    assert result["status"] == "provisioned"
    assert result["comment_posted"] is True
    assert len(azure_client.deployed) == 1
    resource_result = await session.execute(
        __import__("sqlalchemy").select(models.EphemeralResource).filter_by(source_reference="QA-701")
    )
    resource = resource_result.scalars().first()
    comment = format_jira_provision_comment(resource)
    assert "All-inclusive subtotal" in comment
    assert "Estimated Subtotal" in comment
    assert "SSH Access" not in comment

    payload["webhookEvent"] = "jira:issue_updated"
    payload["issue"]["fields"]["status"] = {"name": "Done"}
    teardown = await process_jira_webhook(session, payload, user.id)
    assert teardown["status"] == "teardown_executed"
    assert len(azure_client.deleted) == 1


@pytest.mark.asyncio
async def test_inbound_email_uses_owner_allowlist_and_sends_truthful_reply(monkeypatch, in_memory_db):
    session, user = in_memory_db
    azure_client = await connect_azure(session, user)
    integration = models.IntegrationConfig(
        user_id=user.id,
        email_enabled=True,
        allowed_domains=["company.com"],
        default_ttl_minutes=120,
    )
    session.add(integration)
    await session.commit()
    generated = {"name": "email-storage", "sku": "Standard_LRS", "arm_template": arm_template("zotestemail123")}
    monkeypatch.setattr(resource_chat, "generate_chat_response", lambda *_args, **_kwargs: json.dumps(generated))
    from backend.services import email_service
    messages = []
    monkeypatch.setattr(email_service, "_send_email", lambda **kwargs: messages.append(kwargs) or True)
    payload = schemas.InboundEmailPayload(
        from_email="developer@company.com",
        from_name="Alice Tester",
        to_email="sandbox@company.com",
        subject="Azure storage request",
        body_text="Create a storage account in East US for 2 hours. Azure estimate $0.12/hr.",
        message_id="message-101",
    )

    result = await process_inbound_developer_email(session, payload, owner_user_id=user.id)
    assert result["status"] == "provisioned"
    assert result["email_delivered"] is True
    assert len(azure_client.deployed) == 1
    assert len(messages) == 1
    assert "All-inclusive subtotal" in messages[0]["text_body"]
    assert "Estimated subtotal for 120 minutes" in messages[0]["text_body"]
    assert "public IP" not in messages[0]["text_body"]

    row = (await session.execute(
        __import__("sqlalchemy").select(models.EphemeralResource).filter_by(source_reference="message-101")
    )).scalars().first()
    await destroy_ephemeral_resource(session, row, reason="email lifecycle test")
    duplicate = await process_inbound_developer_email(session, payload, owner_user_id=user.id)
    assert duplicate["status"] == "already_processed"
    assert len(azure_client.deployed) == 1


def test_custom_subtotal_is_single_all_inclusive_amount():
    from backend.services.cost_engine import calculate_custom_subtotal

    quote = calculate_custom_subtotal(0.12, 120)
    data = quote.to_dict()
    assert data["hourly_subtotal"] == 0.146
    assert data["total_subtotal"] == 0.292
    assert data["label"] == "Subtotal"
    assert not any(key in data for key in ("platform_cost", "ai_cost", "breakdown"))
    with pytest.raises(ValueError):
        calculate_custom_subtotal(float("nan"), 60)
