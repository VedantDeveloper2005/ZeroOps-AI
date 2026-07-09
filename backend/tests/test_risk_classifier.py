import pytest
from datetime import datetime, time
from unittest.mock import patch

try:
    from backend.services import risk_classifier
    from backend import config, models
except ImportError:
    from services import risk_classifier
    import config
    import models

def test_is_time_in_window():
    # 1. Standard window within the same day
    window = "02:00-06:00"
    
    # Inside window
    t1 = datetime(2026, 7, 9, 3, 30, 0)
    assert risk_classifier.is_time_in_window(t1, window) is True
    
    # Outside window
    t2 = datetime(2026, 7, 9, 7, 0, 0)
    assert risk_classifier.is_time_in_window(t2, window) is False
    
    # 2. Over-midnight window (e.g. 22:00 to 04:00)
    window_midnight = "22:00-04:00"
    
    # Inside (before midnight)
    t3 = datetime(2026, 7, 9, 23, 0, 0)
    assert risk_classifier.is_time_in_window(t3, window_midnight) is True
    
    # Inside (after midnight)
    t4 = datetime(2026, 7, 9, 1, 0, 0)
    assert risk_classifier.is_time_in_window(t4, window_midnight) is True
    
    # Outside
    t5 = datetime(2026, 7, 9, 12, 0, 0)
    assert risk_classifier.is_time_in_window(t5, window_midnight) is False

def test_classify_by_action_name():
    # Delete operations -> High risk
    assert risk_classifier.classify("delete_resource", {}) == models.RiskTier.high
    assert risk_classifier.classify("remove_aks", {}) == models.RiskTier.high
    
    # IAM/RBAC/Authorization operations -> High risk
    assert risk_classifier.classify("create_role_assignment", {}) == models.RiskTier.high
    assert risk_classifier.classify("update_iam_policy", {}) == models.RiskTier.high
    
    # NSG/Firewall operations -> High risk
    assert risk_classifier.classify("update_nsg_rule", {}) == models.RiskTier.high
    assert risk_classifier.classify("create_firewall", {}) == models.RiskTier.high
    
    # Other operations -> Low risk by default
    assert risk_classifier.classify("create_aks_cluster", {}) == models.RiskTier.low
    assert risk_classifier.classify("list_resources", {}) == models.RiskTier.low

def test_classify_by_cost():
    # Cost below threshold
    params_low_cost = {"estimated_cost_cents": 2000}  # $20
    assert risk_classifier.classify("create_storage_account", params_low_cost) == models.RiskTier.low
    
    # Cost above threshold ($50)
    params_high_cost = {"estimated_cost_cents": 6000}  # $60
    assert risk_classifier.classify("create_storage_account", params_high_cost) == models.RiskTier.high

def test_classify_by_production_outside_window():
    # Production resource outside maintenance window
    params_prod = {"resource_tags": {"environment": "production"}}
    
    # Force maintenance window config to be empty (all production ops high risk)
    with patch.object(config, "MAINTENANCE_WINDOW_UTC", ""):
        assert risk_classifier.classify("scale_aks_nodepool", params_prod) == models.RiskTier.high
        
    # With a specific maintenance window, inside it -> Low risk
    with patch.object(config, "MAINTENANCE_WINDOW_UTC", "02:00-06:00"):
        # Let's mock datetime.utcnow() to return inside window
        with patch("backend.services.risk_classifier.datetime") as mock_dt:
            mock_dt.utcnow.return_value = datetime(2026, 7, 9, 3, 0, 0)
            assert risk_classifier.classify("scale_aks_nodepool", params_prod) == models.RiskTier.low
            
        # Outside window -> High risk
        with patch("backend.services.risk_classifier.datetime") as mock_dt:
            mock_dt.utcnow.return_value = datetime(2026, 7, 9, 12, 0, 0)
            assert risk_classifier.classify("scale_aks_nodepool", params_prod) == models.RiskTier.high
