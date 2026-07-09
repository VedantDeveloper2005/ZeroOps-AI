import logging
import re
from datetime import datetime, time
import uuid

try:
    from backend import config, models
except ImportError:
    import config
    import models

logger = logging.getLogger("zeroops.risk_classifier")

def is_time_in_window(current_time_utc: datetime, window_str: str) -> bool:
    """Check if current UTC time falls within HH:MM-HH:MM window."""
    if not window_str or not re.match(r"^\d{2}:\d{2}-\d{2}:\d{2}$", window_str):
        return False
        
    try:
        start_str, end_str = window_str.split("-")
        sh, sm = map(int, start_str.split(":"))
        eh, em = map(int, end_str.split(":"))
        
        current_time = current_time_utc.time()
        start_time = time(sh, sm)
        end_time = time(eh, em)
        
        if start_time <= end_time:
            return start_time <= current_time <= end_time
        else:
            # Over-midnight window (e.g. 22:00-04:00)
            return current_time >= start_time or current_time <= end_time
    except Exception as e:
        logger.error(f"Error parsing maintenance window {window_str}: {e}")
        return False

def classify(action_type: str, parameters: dict) -> models.RiskTier:
    """Classify the risk tier (low or high) of an Azure operation based on deterministic rules."""
    action = (action_type or "").lower().strip()
    
    # Rule 1: Delete or remove operations
    if "delete" in action or "remove" in action:
        logger.info(f"High risk classified: Delete action detected in '{action_type}'")
        return models.RiskTier.high
        
    # Rule 2: IAM/RBAC or role manipulation
    if any(k in action for k in ["role", "rbac", "iam", "authorization", "policy"]):
        logger.info(f"High risk classified: Authorization/IAM action detected in '{action_type}'")
        return models.RiskTier.high
        
    # Rule 3: NSG, firewall, security rules configuration changes
    if any(k in action for k in ["nsg", "security_rule", "firewall", "security_group", "network_rule"]):
        logger.info(f"High risk classified: Firewall/Security change detected in '{action_type}'")
        return models.RiskTier.high
        
    # Rule 4: Cost above the threshold
    estimated_cost = parameters.get("estimated_cost_cents", 0)
    if estimated_cost > config.RISK_COST_THRESHOLD_CENTS:
        logger.info(f"High risk classified: Cost {estimated_cost} cents exceeds threshold {config.RISK_COST_THRESHOLD_CENTS} cents")
        return models.RiskTier.high
        
    # Rule 5: Production target outside maintenance window
    resource_tags = parameters.get("resource_tags", {})
    # Standardize tags keys and values to lowercase
    normalized_tags = {str(k).lower(): str(v).lower() for k, v in resource_tags.items()}
    
    if normalized_tags.get("environment") == "production":
        current_time_utc = datetime.utcnow()
        in_window = is_time_in_window(current_time_utc, config.MAINTENANCE_WINDOW_UTC)
        if not in_window:
            logger.info(f"High risk classified: Production change requested outside maintenance window ({config.MAINTENANCE_WINDOW_UTC or 'none defined'})")
            return models.RiskTier.high
            
    # Rule 6: Code mutation or package dependency injection (always high risk by default)
    if any(k in action for k in ["dependency", "code", "remediate", "package", "inject"]):
        logger.info(f"High risk classified: Code/Dependency mutation detected in '{action_type}'")
        return models.RiskTier.high

    # Default: Low Risk
    return models.RiskTier.low

