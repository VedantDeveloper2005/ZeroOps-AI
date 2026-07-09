import logging
import uuid
from typing import Any, Dict, Optional

from sqlalchemy.future import select

try:
    from backend import models
    from backend.services import azure_connector, risk_classifier
except ImportError:
    import models
    from services import azure_connector, risk_classifier

logger = logging.getLogger("zeroops.action_gateway")

# Map of action types to their wrapper execution functions
ACTION_DISPATCHER = {
    "create_aks_cluster": azure_connector.create_aks_cluster,
    "update_aks_cluster": azure_connector.update_aks_cluster,
    "scale_aks_nodepool": azure_connector.scale_aks_nodepool,
    "get_aks_cluster": azure_connector.get_aks_cluster,
    "create_vnet": azure_connector.create_vnet,
    "create_storage_account": azure_connector.create_storage_account,
    "delete_resource": azure_connector.delete_resource,
    "list_resources": azure_connector.list_resources
}

def redact_secrets(data: Any) -> Any:
    """Recursively redacts secret-like values from parameter structures."""
    if isinstance(data, dict):
        redacted = {}
        for k, v in data.items():
            # Check key name for common secret substrings
            if any(secret_key in k.lower() for secret_key in ["secret", "password", "token", "key", "cert", "credential", "auth"]):
                redacted[k] = "<REDACTED>"
            else:
                redacted[k] = redact_secrets(v)
        return redacted
    elif isinstance(data, list):
        return [redact_secrets(item) for item in data]
    return data

async def execute_azure_action(
    user_id: uuid.UUID,
    agent_name: str,
    action_type: str,
    parameters: dict,
    db
) -> dict:
    """The single entry point for all agent Azure actions. Classifies risk, creates audit logs, and gates high-risk items."""
    # Redact secrets before saving/logging
    clean_params = redact_secrets(parameters)
    
    # Classify risk
    risk_tier = risk_classifier.classify(action_type, parameters)
    
    # Create audit log entry
    audit_entry = models.AuditLogEntry(
        user_id=user_id,
        agent_name=agent_name,
        action_type=action_type,
        parameters=clean_params,
        risk_tier=risk_tier.value,
        approval_status=models.ApprovalStatus.not_required.value if risk_tier == models.RiskTier.low else models.ApprovalStatus.pending.value,
        result_status=models.AuditResultStatus.pending.value
    )
    
    db.add(audit_entry)
    await db.flush()  # Populates audit_entry.id
    
    if risk_tier == models.RiskTier.high:
        # Create pending approval entry
        pending_approval = models.PendingApproval(
            audit_log_id=audit_entry.id,
            user_id=user_id,
            action_type=action_type,
            parameters=clean_params,
            risk_tier=risk_tier.value,
            status=models.ApprovalStatus.pending.value
        )
        db.add(pending_approval)
        await db.commit()
        
        logger.info(f"High risk action '{action_type}' for user {user_id} blocked. Created pending approval {pending_approval.id}")
        return {
            "status": "pending_approval",
            "approval_id": str(pending_approval.id),
            "audit_log_id": str(audit_entry.id),
            "risk_tier": risk_tier.value,
            "success": True,  # Blocked successfully in gateway
            "detail": "Action requires manager/human approval."
        }
        
    # Low risk - execute immediately
    logger.info(f"Low risk action '{action_type}' for user {user_id} executing immediately.")
    func = ACTION_DISPATCHER.get(action_type)
    if not func:
        res = {"success": False, "error": f"Unsupported action type: {action_type}"}
    else:
        try:
            res = await func(user_id, parameters, db)
        except Exception as e:
            res = {"success": False, "error": str(e)}
            
    audit_entry.result_status = models.AuditResultStatus.success.value if res.get("success") else models.AuditResultStatus.failed.value
    audit_entry.result_detail = res.get("detail") or res.get("error")
    await db.commit()
    
    return res

async def decide_pending_action(
    approval_id: uuid.UUID,
    decision: str,
    decided_by: uuid.UUID,
    db
) -> dict:
    """Submit approval/denial for a pending action."""
    result = await db.execute(
        select(models.PendingApproval).filter(models.PendingApproval.id == approval_id)
    )
    pending = result.scalars().first()
    if not pending:
        return {"success": False, "error": "Pending approval entry not found."}
        
    if pending.status != models.ApprovalStatus.pending.value:
        return {"success": False, "error": f"Approval has already been decided: {pending.status}"}
        
    result_audit = await db.execute(
        select(models.AuditLogEntry).filter(models.AuditLogEntry.id == pending.audit_log_id)
    )
    audit = result_audit.scalars().first()
    
    if decision == "denied":
        pending.status = models.ApprovalStatus.denied.value
        pending.decided_by = decided_by
        pending.decided_at = models.datetime.utcnow()
        
        if audit:
            audit.approval_status = models.ApprovalStatus.denied.value
            audit.approved_by = decided_by
            audit.result_status = models.AuditResultStatus.failed.value
            audit.result_detail = "Denied by administrator."
            
        await db.commit()
        return {"success": True, "detail": "Action was successfully denied/rejected."}
        
    elif decision == "approved":
        pending.status = models.ApprovalStatus.approved.value
        pending.decided_by = decided_by
        pending.decided_at = models.datetime.utcnow()
        
        if audit:
            audit.approval_status = models.ApprovalStatus.approved.value
            audit.approved_by = decided_by
            
        await db.commit()
        
        # Execute the action now
        logger.info(f"Approved action '{pending.action_type}' (Approval: {pending.id}) executing.")
        func = ACTION_DISPATCHER.get(pending.action_type)
        if not func:
            res = {"success": False, "error": f"Unsupported action type: {pending.action_type}"}
        else:
            try:
                res = await func(pending.user_id, pending.parameters, db)
            except Exception as e:
                res = {"success": False, "error": str(e)}
                
        # Re-fetch audit to avoid session desync
        result_audit = await db.execute(
            select(models.AuditLogEntry).filter(models.AuditLogEntry.id == pending.audit_log_id)
        )
        audit = result_audit.scalars().first()
        if audit:
            audit.result_status = models.AuditResultStatus.success.value if res.get("success") else models.AuditResultStatus.failed.value
            audit.result_detail = res.get("detail") or res.get("error")
            
        await db.commit()
        return res
        
    return {"success": False, "error": "Invalid decision. Must be approved or denied."}
