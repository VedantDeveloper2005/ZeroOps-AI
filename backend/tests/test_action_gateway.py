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
    
    # Configure mock user connection status to connected and store mock secret
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
    
    # We call a low-risk action "list_resources" which executes immediately
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
    
    # Cleanup vault
    azure_connector.delete_credential_from_vault(user.id)

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
    assert "deleted successfully" in audit.result_detail
    
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

@pytest.mark.asyncio
async def test_cost_risk_rule_integration(db_session):
    result_user = await db_session.execute(select(models.User))
    user = result_user.scalars().first()
    
    # Create a project
    project = models.Project(
        id=uuid.uuid4(),
        user_id=user.id,
        name="test-project",
        full_name="test-org/test-project",
        framework="nextjs",
        language="typescript"
    )
    db_session.add(project)
    
    # Create an environment (production)
    env = models.Environment(
        id=uuid.uuid4(),
        project_id=project.id,
        name="production"
    )
    db_session.add(env)
    
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
    
    from backend.services.agent import NvidiaNIMDevOpsAgent
    agent_instance = NvidiaNIMDevOpsAgent()
    
    # Scale request with 10 nodes (at $100/node = $1000, exceeding $50 threshold)
    success = await agent_instance.scale_resources(
        project_id=str(project.id),
        min_replicas=1,
        max_replicas=10,
        db=db_session
    )
    
    assert success is True
    
    # Assert that a PendingApproval was created for the scale action
    result_pending = await db_session.execute(
        select(models.PendingApproval).filter(models.PendingApproval.user_id == user.id)
    )
    pending = result_pending.scalars().first()
    assert pending is not None
    assert pending.action_type == "scale_aks_nodepool"
    assert pending.parameters["node_count"] == 10
    assert pending.parameters["estimated_cost_cents"] == 100000  # 10 * 10000 cents = 100,000 cents
    assert pending.parameters["resource_tags"]["environment"] == "production"
    
    azure_connector.delete_credential_from_vault(user.id)

@pytest.mark.asyncio
async def test_auto_remediate_package_check_and_gating(db_session):
    result_user = await db_session.execute(select(models.User))
    user = result_user.scalars().first()
    
    project = models.Project(
        id=uuid.uuid4(),
        user_id=user.id,
        name="healing-project",
        full_name="test-org/healing-project",
        framework="nextjs",
        language="typescript"
    )
    db_session.add(project)
    
    deployment = models.Deployment(
        id=uuid.uuid4(),
        project_id=project.id,
        user_id=user.id,
        status="failed",
        environment="production"
    )
    db_session.add(deployment)
    
    fa = models.FailureAnalysis(
        id=uuid.uuid4(),
        project_id=project.id,
        deployment_id=deployment.id,
        user_id=user.id,
        failure_summary="missing dependency 'non-existent-package-abc-123'",
        root_cause="compilation failure",
        recommended_fix="install 'non-existent-package-abc-123'",
        severity="error"
    )
    db_session.add(fa)
    await db_session.commit()
    
    from backend.services.agent import NvidiaNIMDevOpsAgent
    agent_instance = NvidiaNIMDevOpsAgent()
    
    # Mock git.get_repo_path to return a valid directory containing package.json
    import tempfile
    import os
    import json
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create mock package.json
        with open(os.path.join(tmpdir, "package.json"), "w") as f:
            json.dump({"dependencies": {}}, f)
            
        with patch("backend.services.git.get_repo_path") as mock_repo_path:
            mock_repo_path.return_value = tmpdir
            
            # 1. Attempt remediation with non-existent package. Should return False (refused).
            success = await agent_instance.auto_remediate_failure(
                deployment_id=str(deployment.id),
                failure_reason="missing dependency 'non-existent-package-abc-123'",
                db=db_session
            )
            assert success is False
            
            # 2. Attempt remediation with a valid real package name (e.g. "lodash").
            fa.failure_summary = "missing dependency 'lodash'"
            fa.recommended_fix = "install 'lodash'"
            await db_session.commit()
            
            # Store connection first
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
            
            success_ok = await agent_instance.auto_remediate_failure(
                deployment_id=str(deployment.id),
                failure_reason="missing dependency 'lodash'",
                db=db_session
            )
            assert success_ok is True
            
            # Verify pending approval was created for "inject_dependency"
            result_pending = await db_session.execute(
                select(models.PendingApproval).filter(models.PendingApproval.action_type == "inject_dependency")
            )
            pending = result_pending.scalars().first()
            assert pending is not None
            assert pending.parameters["package_name"] == "lodash"
            assert pending.status == "pending"
            
            # Approve it and verify file was written to disk
            await action_gateway.decide_pending_action(
                approval_id=pending.id,
                decision="approved",
                decided_by=user.id,
                db=db_session
            )
            
            # Verify lodash is now in the package.json
            with open(os.path.join(tmpdir, "package.json"), "r") as f:
                data = json.load(f)
            assert data["dependencies"]["lodash"] == "latest"
            
            azure_connector.delete_credential_from_vault(user.id)

