"""
Stub for Step 8 Swap-Readiness.
Proves we can easily drop in a real VAHAN / eGujCop API integration by simply extending BasePlateRegistry.
"""
from __future__ import annotations

from registry.base_plate_registry import BasePlateRegistry, RegistryRecord

class RealRegistryAPI(BasePlateRegistry):
    def __init__(self, api_url: str, auth_token: str):
        self.api_url = api_url
        self.auth_token = auth_token
        
    def connect(self) -> None:
        """Authenticate against the external API (stub: no-op)."""
        pass

    def lookup(self, plate_number: str) -> RegistryRecord | None:
        """
        Query a real government database.
        
        Example implementation:
        import requests
        response = requests.get(
            f"{self.api_url}/search?plate={plate_number}", 
            headers={"Authorization": self.auth_token}
        )
        if response.status_code == 200:
            data = response.json()
            return RegistryRecord(
                plate_number=plate_number,
                status=data.get("status", "clear"),
                flags=data.get("flags", []),
                owner_info={"owner": data.get("owner"), "make": data.get("make")}
            )
        return None
        """
        # Stub implementation always returns None (not found)
        return None
