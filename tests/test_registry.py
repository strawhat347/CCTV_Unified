"""
tests/test_registry.py - Tests for the mock registry.
"""
import pytest
from registry.mock_registry import MockRegistry

def test_registry_lookup():
    registry = MockRegistry(csv_path="data/seed_registry.csv")
    registry.connect()

    # Clear plate
    record = registry.lookup("GJ05CD6789")
    assert record is not None
    assert record.status == "clear"
    assert record.owner_info["owner_name"] == "Rahul Sharma"

    # Stolen plate
    record2 = registry.lookup("mh12ab1234") # case insensitive
    assert record2 is not None
    assert record2.status == "stolen"
    assert "reported_stolen_mumbai" in record2.flags

    # Unknown plate
    record3 = registry.lookup("XYZ123")
    assert record3 is None
