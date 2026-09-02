"""
registry/real_registry_api.py — Real registry API client (not yet implemented).

This module will eventually connect to a real vehicle registration database API.
Currently raises NotImplementedError to prevent silent failures.
"""

import logging
from typing import Optional
from registry.base_plate_registry import BasePlateRegistry, RegistryRecord

logger = logging.getLogger("real_registry_api")


class RealRegistryAPI(BasePlateRegistry):
    """
    Placeholder for a real vehicle registration database API.
    Not yet implemented — will raise NotImplementedError if invoked.
    """

    def connect(self):
        logger.warning(
            "RealRegistryAPI.connect() called but real registry is not yet implemented. "
            "Set MODE=mock in .env to use the mock registry."
        )

    def lookup(self, plate_number: str) -> Optional[RegistryRecord]:
        raise NotImplementedError(
            "RealRegistryAPI.lookup() is not yet implemented. "
            "Set MODE=mock in your .env to use the mock registry instead."
        )
