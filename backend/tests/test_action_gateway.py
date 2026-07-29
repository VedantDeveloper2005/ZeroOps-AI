import pytest
import pytest_asyncio
import uuid
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from unittest.mock import patch, MagicMock

try:
    from backend import models, config
    from backend.services import action_gateway, azure_connector
except ImportError:
    import models
    import config
    from services import action_gateway, azure_connector

# Setup in-memory async SQLite database for testing database interactions
async_engine = create_async_engine("sqlite+aiosqlite:///:memory:", connect_args={"check_same_thread": False})
AsyncSessionLocal = sessionmaker(
    async_engine,
    class_=AsyncSession,
    expire_on_commit=False
)

@pytest_asyncio.fixture(scope="function")
async def db_session():
    async with async_engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.create_all)
        
    async with AsyncSessionLocal() as session:
        # Pre-populate a test user
        user = models.User(
            id=uuid.uuid4(),
            email="admin@zeroops.ai",
            first_name="Admin",
            last_name="ZeroOps",
            plan="enterprise"
        )
        session.add(user)
        await session.commit()
        
        yield session
        
    async with async_engine.begin() as conn:
        await conn.run_sync(models.Base.metadata.drop_all)

@pytest.mark.asyncio
async def test_execute_low_risk_action(db_session):
    # Retrieve user
    result_user = await db_session.execute(select(models.User))
    user = result_user.scalars().first()
    assert user is not None
    
    async def list_resources(*args, **kwargs):
        return {"success": True, "resources": []}

    # Unit tests replace the Azure SDK boundary explicitly; application code has
    # no mock credential or local-vault fallback.
    with patch.dict(action_gateway.ACTION_DISPATCHER, {"list_resources": list_resources}):
        res = await action_gateway.execute_azure_action(
            user_id=user.id,
            agent_name="scaling_agent",
            action_type="list_resources",
            parameters={},
            db=db_session
        )
    
    assert res.get("success") is True
    assert "resources" in res
    
    # Check that audit log entry was created with success status and not_required approval
    result_audit = await db_session.execute(
        select(models.AuditLogEntry).filter(models.AuditLogEntry.user_id == user.id)
    )
    audit_log = result_audit.scalars().first()
    assert audit_log is not None
    assert audit_log.action_type == "list_resources"
    assert audit_log.risk_tier == "low"
    assert audit_log.approval_status == "not_required"
    assert audit_log.result_status == "success"
    
    # Ensure no pending approval entry exists
    result_pending = await db_session.execute(
        select(models.PendingApproval).filter(models.PendingApproval.user_id == user.id)
    )
    pending = result_pending.scalars().first()
    assert pending is None
    
@pytest.mark.asyncio
async def test_execute_high_risk_action_blocks(db_session):
    result_user = await db_session.execute(select(models.User))
    user = result_user.scalars().first()
    
    # Configure connection status to connected
    conn = models.UserAzureConnection(
        user_id=user.id,
        tenant_id="mock",
        client_id="mock",
        subscription_id="mock-sub",
        resource_group="mock-rg",
        connection_status="connected"
    )
    db_session.add(conn)
    azure_connector.store_credential_in_vault(user.id, "mock")
    await db_session.commit()
    
    # High risk action: delete_resource
    res = await action_gateway.execute_azure_action(
        user_id=user.id,
        agent_name="scaling_agent",
        action_type="delete_resource",
        parameters={"resource_id": "test-res-id"},
        db=db_session
    )
    
    # The action should be blocked and return pending approval info
    assert res.get("status") == "pending_approval"
    assert "approval_id" in res
    assert "audit_log_id" in res
    
    # Verify audit log exists as pending
    result_audit = await db_session.execute(
        select(models.AuditLogEntry).filter(models.AuditLogEntry.user_id == user.id)
    )
    audit_log = result_audit.scalars().first()
    assert audit_log is not None
    assert audit_log.action_type == "delete_resource"
    assert audit_log.risk_tier == "high"
    assert audit_log.approval_status == "pending"
    assert audit_log.result_status == "pending"
    
    # Verify pending approval entry exists in database
    result_pending = await db_session.execute(
        select(models.PendingApproval).filter(models.PendingApproval.id == uuid.UUID(res["approval_id"]))
    )
    pending = result_pending.scalars().first()
    assert pending is not None
    assert pending.status == "pending"
    assert pending.action_type == "delete_resource"
    assert pending.parameters["resource_id"] == "test-res-id"
    
    azure_connector.delete_credential_from_vault(user.id)
@pytest.mark.asyncio
async def test_decide_approval_approve(db_session):
    result_user = await db_session.execute(select(models.User))
    user = result_user.scalars().first()
    
    # Create block state manually
    audit = models.AuditLogEntry(
        user_id=user.id,
        agent_name="scaling_agent",
        action_type="delete_resource",
        parameters={"resource_id": "test-res-id"},
        risk_tier="high",
        approval_status="pending",
        result_status="pending"
    )
    db_session.add(audit)
    await db_session.flush()
    
    pending = models.PendingApproval(
        audit_log_id=audit.id,
        user_id=user.id,
        action_type="delete_resource",
        parameters={"resource_id": "test-res-id"},
        raw_parameters={"resource_id": "test-res-id"},
        risk_tier="high",
        status="pending"
    )
    db_session.add(pending)
    await db_session.commit()
    
    # Approve the action using the decider endpoint logic
    async def delete_resource(*args, **kwargs):
        return {"success": True, "detail": "Deleted by test double."}

    with patch.dict(action_gateway.ACTION_DISPATCHER, {"delete_resource": delete_resource}):
        decision_res = await action_gateway.decide_pending_action(
            approval_id=pending.id,
            decision="approved",
            decided_by=user.id,
            db=db_session
        )
    
    assert decision_res.get("success") is True
    
    # Ensure database states are updated to approved/success
    await db_session.refresh(pending)
    await db_session.refresh(audit)
    
    assert pending.status == "approved"
    assert pending.decided_by == user.id
    assert audit.approval_status == "approved"
    assert audit.result_status == "success"
    assert audit.result_detail == "Deleted by test double."
    
    azure_connector.delete_credential_from_vault(user.id)

@pytest.mark.asyncio
async def test_decide_approval_deny(db_session):
    result_user = await db_session.execute(select(models.User))
    user = result_user.scalars().first()
    
    audit = models.AuditLogEntry(
        user_id=user.id,
        agent_name="scaling_agent",
        action_type="delete_resource",
        parameters={"resource_id": "test-res-id"},
        risk_tier="high",
        approval_status="pending",
        result_status="pending"
    )
    db_session.add(audit)
    await db_session.flush()
    
    pending = models.PendingApproval(
        audit_log_id=audit.id,
        user_id=user.id,
        action_type="delete_resource",
        parameters={"resource_id": "test-res-id"},
        raw_parameters={"resource_id": "test-res-id"},
        risk_tier="high",
        status="pending"
    )
    db_session.add(pending)
    await db_session.commit()
    
    # Deny the action
    decision_res = await action_gateway.decide_pending_action(
        approval_id=pending.id,
        decision="denied",
        decided_by=user.id,
        db=db_session
    )
    
    assert decision_res.get("success") is True
    
    await db_session.refresh(pending)
    await db_session.refresh(audit)
    
    assert pending.status == "denied"
    assert audit.approval_status == "denied"
    assert audit.result_status == "failed"
    assert "Denied by administrator" in audit.result_detail

@pytest.mark.asyncio
async def test_unredacted_parameter_execution_regression(db_session):
    result_user = await db_session.execute(select(models.User))
    user = result_user.scalars().first()
    
    conn = models.UserAzureConnection(
        user_id=user.id,
        tenant_id="mock",
        client_id="mock",
        subscription_id="mock-sub",
        resource_group="mock-rg",
        connection_status="connected"
    )
    db_session.add(conn)
    azure_connector.store_credential_in_vault(user.id, "mock")
    await db_session.commit()
    
    # Execute high-risk action through gateway. Parameters contain a "key" word.
    res = await action_gateway.execute_azure_action(
        user_id=user.id,
        agent_name="scaling_agent",
        action_type="delete_resource",
        parameters={"resource_id": "test-res-id", "ssh_public_key": "actual-value-123"},
        db=db_session
    )
    
    approval_id = uuid.UUID(res["approval_id"])
    result_pending = await db_session.execute(
        select(models.PendingApproval).filter(models.PendingApproval.id == approval_id)
    )
    pending = result_pending.scalars().first()
    
    # Assert parameters are redacted for DB/UI
    assert pending.parameters["ssh_public_key"] == "<REDACTED>"
    # Assert raw_parameters are unredacted for execution
    assert pending.raw_parameters["ssh_public_key"] == "actual-value-123"
    
    # Approve the action, and intercept the call to verify it gets the raw parameters
    from unittest.mock import AsyncMock
    mock_delete = AsyncMock(return_value={"success": True, "detail": "Success"})
    
    with patch.dict(action_gateway.ACTION_DISPATCHER, {"delete_resource": mock_delete}):
        await action_gateway.decide_pending_action(
            approval_id=approval_id,
            decision="approved",
            decided_by=user.id,
            db=db_session
        )
        
        # Assert the real SDK wrapper function received the raw, unredacted parameters
        mock_delete.assert_called_once()
        called_args = mock_delete.call_args[0]
        assert called_args[1]["ssh_public_key"] == "actual-value-123"
        
    azure_connector.delete_credential_from_vault(user.id)
