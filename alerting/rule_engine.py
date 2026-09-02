"""
alerting/rule_engine.py - Evaluates detections against registry records.
"""
import logging
from typing import Optional

from alerting.alert_dispatcher import dispatch_alert
from registry.base_plate_registry import BasePlateRegistry

logger = logging.getLogger("rule_engine")

class RuleEngine:
    def __init__(self, registry: BasePlateRegistry):
        self.registry = registry

    def process_detection(self, detection_id: int, camera_id: int, plate_text: Optional[str]) -> None:
        """
        Evaluate a single detection row to see if it warrants an alert.
        """
        if not plate_text:
            return

        # Look up the plate in the registry (using fuzzy matching to catch OCR errors)
        try:
            record = self.registry.fuzzy_lookup(plate_text, threshold=0.85)
        except RuntimeError as e:
            logger.error(f"Registry lookup failed for {plate_text}: {e}")
            return

        if record is None:
            # Plate not in registry. Depending on use case, could trigger an "unregistered" alert.
            # But for now, we ignore unknown plates.
            return
            
        # Define triggering statuses
        if record.status in ("stolen", "flagged"):
            # If the OCR text doesn't exactly match the registry record, it's a fuzzy match
            import difflib
            import copy
            
            # Create a copy so we don't mutate the mock registry's global state
            alert_record = copy.deepcopy(record)
            
            if difflib.SequenceMatcher(None, plate_text.upper(), record.plate_number.upper()).ratio() < 1.0:
                alert_record.status = f"probable {record.status} match"

            # Trigger alert!
            dispatch_alert(
                camera_id=camera_id,
                detection_id=detection_id,
                plate_text=plate_text,
                record=alert_record
            )
