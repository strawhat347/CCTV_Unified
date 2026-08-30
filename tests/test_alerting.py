"""
tests/test_alerting.py - Tests for the rule engine and alert dispatcher.
"""
from unittest.mock import patch, MagicMock
from alerting.rule_engine import RuleEngine
from registry.base_plate_registry import RegistryRecord

@patch("alerting.rule_engine.dispatch_alert")
def test_rule_engine_triggers_alerts(mock_dispatch):
    # Mock registry
    mock_registry = MagicMock()
    
    # Return a clear record for Plate 1
    mock_registry.fuzzy_lookup.return_value = RegistryRecord(
        plate_number="GJ05CD6789", status="clear"
    )
    
    engine = RuleEngine(registry=mock_registry)
    engine.process_detection(1, 100, "GJ05CD6789")
    mock_dispatch.assert_not_called()
    
    # Return a stolen record for Plate 2
    mock_registry.fuzzy_lookup.return_value = RegistryRecord(
        plate_number="MH12AB1234", status="stolen", flags=["reported"]
    )
    
    engine.process_detection(2, 100, "MH12AB1234")
    mock_dispatch.assert_called_once()
    
    args, kwargs = mock_dispatch.call_args
    assert kwargs["plate_text"] == "MH12AB1234"
    assert kwargs["detection_id"] == 2
