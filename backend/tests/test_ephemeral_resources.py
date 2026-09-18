"""
Unit & Integration Tests for Ephemeral Cloud Sandboxes & Third-Party Integrations
"""

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from backend import models, schemas
from backend.services.ephemeral_resources import (
    RESOURCE_CATALOG,
    REGIONS,
    get_hourly_cost,
    provision_ephemeral_resource,
    extend_ephemeral_resource,
    destroy_ephemeral_resource,
    reap_expired_ephemeral_resources,
)
from backend.services.resource_chat import parse_intent_rule_based, process_resource_chat
from backend.services.jira_service import (
    process_jira_webhook,
    format_jira_provision_comment,
    format_jira_destroy_comment,
)
from backend.services.inbound_email_service import (
    process_inbound_developer_email,
    generate_developer_reply_email,
)


@pytest_asyncio.fixture
async def in_memory_db():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)
    async with engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)

    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with async_session() as session:
        # Create a test user
        test_user = models.User(
            id=uuid.uuid4(),
            email="developer@company.com",
            first_name="Alice",
            last_name="Tester",
        )
        session.add(test_user)
        await session.commit()
        await session.refresh(test_user)
        yield session, test_user

    await engine.dispose()


def test_catalog_structure():
    """Verify that all standard resource types exist with SKUs and regions."""
    expected_types = [
        "vm_linux",
        "vm_windows",
        "database_postgres",
        "database_mysql",
        "container_app",
        "storage_account",
        "redis_cache",
    ]
    for rtype in expected_types:
        assert rtype in RESOURCE_CATALOG
        cat = RESOURCE_CATALOG[rtype]
        assert "default_sku" in cat
        assert len(cat["skus"]) > 0
        assert "default_ports" in cat

    assert len(REGIONS) >= 5
    assert any(r["id"] == "eastus" for r in REGIONS)
    assert get_hourly_cost("vm_linux", "Standard_B2s") > 0


def test_natural_language_intent_extraction():
    """Test AI intent extraction from natural language messages."""
    # 1. Linux VM with Docker and 3 hours
    msg1 = "I need a 4-core Linux VM with Docker in East US for 3 hours to run stress tests"
    intent1 = parse_intent_rule_based(msg1)
    assert intent1["action"] == "propose_resource"
    assert intent1["resource_type"] == "vm_linux"
    assert intent1["region"] == "eastus"
    assert intent1["ttl_minutes"] == 180
    assert intent1["startup_script"] is not None
    assert "docker" in intent1["startup_script"]

    # 2. Postgres database request
    msg2 = "Spin up a test PostgreSQL database in West Europe for 2 hours"
    intent2 = parse_intent_rule_based(msg2)
    assert intent2["resource_type"] == "database_postgres"
    assert intent2["region"] == "westeurope"
    assert intent2["ttl_minutes"] == 120

    # 3. Windows VM with RDP
    msg3 = "Deploy a Windows Server VM with RDP"
    intent3 = parse_intent_rule_based(msg3)
    assert intent3["resource_type"] == "vm_windows"
    assert 3389 in intent3["open_ports"]

    # 4. Lifecycle commands
    assert parse_intent_rule_based("Extend my VM by 1 hour")["action"] == "extend_ttl"
    assert parse_intent_rule_based("Destroy the sandbox now")["action"] == "destroy_resource"
    assert parse_intent_rule_based("What sandboxes are currently running?")["action"] == "query_status"


@pytest.mark.asyncio
async def test_process_resource_chat(in_memory_db):
    """Test full conversational chat assistant producing proposal cards."""
    session, user = in_memory_db
    res = await process_resource_chat(
        message="I need an Ubuntu VM with Docker for 2 hours",
        user=user,
        active_resources_count=1,
    )
    assert res.action_detected == "propose_resource"
    assert res.proposed_resource is not None
    assert res.proposed_resource.resource_type == "vm_linux"
    assert res.proposed_resource.ttl_minutes == 120
    assert "Linux Virtual Machine" in res.reply or "Ubuntu" in str(res.proposed_resource.os_distro)


@pytest.mark.asyncio
async def test_provision_and_lifecycle(in_memory_db):
    """Test provisioning, extending TTL, and destroying an ephemeral resource."""
    session, user = in_memory_db

    req = schemas.EphemeralResourceCreateRequest(
        name="test-runner",
        resource_type="vm_linux",
        region="eastus",
        sku="Standard_B2s",
        ttl_minutes=120,
        startup_script="#!/bin/bash\necho hello",
    )

    # 1. Provision
    resource = await provision_ephemeral_resource(
        db=session,
        user=user,
        request=req,
        source="catalog_ui",
    )
    assert resource.status == "active"
    assert resource.connection_info.get("public_ip") is not None
    assert resource.connection_info.get("ssh_command") is not None
    expires = resource.expires_at.replace(tzinfo=timezone.utc) if resource.expires_at.tzinfo is None else resource.expires_at
    assert expires > datetime.now(timezone.utc)
    original_expiry = expires

    # 2. Extend
    extended = await extend_ephemeral_resource(
        db=session,
        user_id=user.id,
        resource_id=resource.id,
        extend_minutes=60,
    )
    new_expiry = extended.expires_at.replace(tzinfo=timezone.utc) if extended.expires_at.tzinfo is None else extended.expires_at
    assert new_expiry > original_expiry
    assert extended.ttl_minutes == 180

    # 3. Destroy
    destroyed = await destroy_ephemeral_resource(
        db=session,
        resource=extended,
        reason="Manual user teardown",
    )
    assert destroyed.status == "destroyed"
    assert destroyed.destroyed_at is not None


@pytest.mark.asyncio
async def test_auto_destroy_reaper(in_memory_db):
    """Test background TTL daemon reaps resources whose expires_at is past."""
    session, user = in_memory_db

    req = schemas.EphemeralResourceCreateRequest(
        name="expired-sandbox",
        resource_type="database_postgres",
        region="eastus",
        sku="Standard_B1ms",
        ttl_minutes=30,
    )
    resource = await provision_ephemeral_resource(session, user, req)

    # Backdate expires_at to simulate expiration
    resource.expires_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    await session.commit()
    await session.refresh(resource)

    reaped_count = await reap_expired_ephemeral_resources(session)
    assert reaped_count == 1

    await session.refresh(resource)
    assert resource.status == "destroyed"


@pytest.mark.asyncio
async def test_jira_webhook_provision_and_teardown(in_memory_db):
    """Test Jira webhook parsing, resource provisioning, and resolution teardown."""
    session, user = in_memory_db

    create_payload = {
        "webhookEvent": "jira:issue_created",
        "issue": {
            "key": "QA-701",
            "fields": {
                "summary": "Need test VM for checkout load testing",
                "description": "Please provision a 4-core Ubuntu VM with Docker in East US for 3 hours.",
                "labels": ["zeroops-sandbox"],
                "status": {"name": "In Progress"},
            },
        },
    }

    # Provision via webhook
    result = await process_jira_webhook(session, create_payload, fallback_user_id=user.id)
    assert result["status"] == "provisioned"
    assert result["issue_key"] == "QA-701"
    assert "generated_jira_comment" in result
    assert "ZeroOps AI" in result["generated_jira_comment"]
    assert "SSH Access" in result["generated_jira_comment"]

    # Mark ticket Done -> automated teardown
    close_payload = {
        "webhookEvent": "jira:issue_updated",
        "issue": {
            "key": "QA-701",
            "fields": {
                "summary": "Need test VM for checkout load testing",
                "status": {"name": "Done"},
            },
        },
    }
    teardown_result = await process_jira_webhook(session, close_payload, fallback_user_id=user.id)
    assert teardown_result["status"] == "teardown_executed"
    assert teardown_result["issue_key"] == "QA-701"


@pytest.mark.asyncio
async def test_inbound_email_developer_request(in_memory_db, monkeypatch):
    """Test developer emailing ops address, provisioning sandbox, and sending reply email."""
    session, user = in_memory_db

    # Mock outbound email sender
    sent_emails = []
    def fake_send_email(to_email, subject, html_body, text_body):
        sent_emails.append({"to": to_email, "subject": subject, "html": html_body, "text": text_body})
        return True

    from backend.services import email_service
    monkeypatch.setattr(email_service, "_send_email", fake_send_email)

    payload = schemas.InboundEmailPayload(
        from_email=user.email,
        from_name="Alice Tester",
        to_email="sandbox@zeroops.ai",
        subject="Request for test Postgres DB",
        body_text="Hi Ops, please spin up a test PostgreSQL database in East US for 2 hours. Thanks!",
    )

    result = await process_inbound_developer_email(session, payload)
    assert result["status"] == "provisioned"
    assert result["recipient"] == user.email
    assert result["email_delivered"] is True
    assert len(sent_emails) == 1
    assert "Your Cloud Sandbox is Ready" in sent_emails[0]["html"]
    assert "postgresql://" in sent_emails[0]["text"]
    assert "Hourly Subtotal" in sent_emails[0]["html"]
    assert "Hourly Subtotal" in sent_emails[0]["text"]


def test_rigid_cost_engine_calculations():
    """Verify rigid cost calculations combine resource aspects, platform ops, and AI into Subtotal."""
    from backend.services.cost_engine import calculate_hourly_subtotal, calculate_subtotal

    # 1. Standard Linux VM (Standard_B2s: 2 vCPUs, 4GB RAM)
    # Compute: (2 * 0.012) + (4 * 0.004) = 0.040
    # Net/Disk: 0.006 => Resource Aspects = 0.046
    # Platform: 0.012 + (0.046 * 0.05) = 0.0143
    # AI: 0.008
    # Subtotal: 0.046 + 0.0143 + 0.008 = 0.0683 => 0.068
    b2s_linux_rate = calculate_hourly_subtotal("vm_linux", "Standard_B2s")
    assert b2s_linux_rate == 0.068

    # 2. Windows VM (Standard_B2s: includes Windows licensing: 2 * 0.024 = 0.048)
    # Subtotal: 0.119
    b2s_windows_rate = calculate_hourly_subtotal("vm_windows", "Standard_B2s", os_distro="Windows Server 2022")
    assert b2s_windows_rate == 0.119
    assert b2s_windows_rate > b2s_linux_rate  # Windows licensing correctly incorporated

    # 3. Database Postgres (Standard_B1ms: includes managed engine overhead $0.015/hr)
    pg_rate = calculate_hourly_subtotal("database_postgres", "Standard_B1ms")
    assert pg_rate == 0.063

    # 4. Multi-hour SubtotalQuote scaling
    quote_3h = calculate_subtotal("vm_linux", "Standard_B2s", duration_minutes=180)
    assert quote_3h.hourly_subtotal == 0.068
    assert quote_3h.total_subtotal == round(0.068 * 3.0, 3)
    assert quote_3h.label == "Subtotal"


def test_rigid_cost_engine_strictly_omits_separate_platform_ai_breakdown():
    """CRITICAL: Ensure platform and AI costs are NOT exposed as separate line items or breakdown keys."""
    from backend.services.cost_engine import calculate_subtotal

    quote = calculate_subtotal("vm_linux", "Standard_B2s", duration_minutes=120)
    quote_dict = quote.to_dict()

    # Must only expose unified subtotal fields
    assert "hourly_subtotal" in quote_dict
    assert "total_subtotal" in quote_dict
    assert quote_dict["label"] == "Subtotal"

    # MUST NOT expose separate platform or AI fees
    forbidden_keys = [
        "platform_cost",
        "platform_fee",
        "platform_price",
        "ai_cost",
        "ai_fee",
        "ai_price",
        "breakdown",
    ]
    for key in forbidden_keys:
        assert key not in quote_dict, f"Leaked separate fee '{key}' in client quote!"


@pytest.mark.asyncio
async def test_chat_proposal_and_serialization_subtotal(in_memory_db):
    """Verify EphemeralResourceProposal and serialized response include hourly_subtotal and total_subtotal."""
    from backend.routes.ephemeral_resources import _serialize_resource

    session, user = in_memory_db

    # 1. Chat proposal
    res = await process_resource_chat(
        message="Provision a Linux VM for 2 hours",
        user=user,
    )
    prop = res.proposed_resource
    assert prop is not None
    assert prop.hourly_subtotal is not None
    assert prop.total_subtotal is not None
    assert prop.hourly_subtotal == 0.068
    assert prop.total_subtotal == 0.136
    assert "Hourly Subtotal" in res.reply
    assert "Estimated Subtotal" in res.reply
    # Ensure no separate platform/AI line item leaked
    assert "Platform fee" not in res.reply
    assert "AI fee" not in res.reply

    # 2. Provision and serialization
    req = schemas.EphemeralResourceCreateRequest(
        name="subtotal-test",
        resource_type="vm_linux",
        region="eastus",
        sku="Standard_B2s",
        ttl_minutes=120,
    )
    db_res = await provision_ephemeral_resource(session, user, req)
    serialized = _serialize_resource(db_res)
    assert serialized.hourly_subtotal == 0.068
    assert serialized.total_subtotal == 0.136


def test_jira_provision_comment_includes_subtotal_only():
    """Verify Jira comment includes Hourly Subtotal and does not leak separate platform/AI line items."""
    fake_resource = models.EphemeralResource(
        id=uuid.uuid4(),
        user_id=uuid.uuid4(),
        name="jira-sandbox",
        resource_type="vm_linux",
        region="eastus",
        sku="Standard_B2s",
        status="active",
        ttl_minutes=120,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=2),
        cost_estimate_hourly=0.068,
        connection_info={"public_ip": "20.120.45.10", "ssh_command": "ssh azureuser@20.120.45.10"},
    )
    comment = format_jira_provision_comment(fake_resource)
    assert "*Hourly Subtotal:* $0.068/hr" in comment
    assert "Platform fee" not in comment
    assert "AI fee" not in comment

