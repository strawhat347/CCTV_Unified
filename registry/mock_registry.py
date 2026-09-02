"""
registry/mock_registry.py - Mock plate registry using a local CSV file.
"""

from __future__ import annotations

import csv
import difflib
from pathlib import Path
from typing import Optional

from registry.base_plate_registry import BasePlateRegistry, RegistryRecord


class MockRegistry(BasePlateRegistry):
    def __init__(self, csv_path: str = "data/seed_registry.csv"):
        self.csv_path = Path(csv_path)
        self._data: dict[str, RegistryRecord] = {}
        self._connected = False

    def connect(self) -> None:
        self._data.clear()
        if not self.csv_path.exists():
            raise FileNotFoundError(f"Registry seed file not found: {self.csv_path}")

        with open(self.csv_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                plate = row["plate_number"].strip().upper()
                status = row["status"].strip().lower()
                flags_raw = row.get("flags", "")
                flags = [f.strip() for f in flags_raw.split(",")] if flags_raw else []
                
                owner_info = {
                    "owner_name": row.get("owner_name", ""),
                    "vehicle_make": row.get("vehicle_make", ""),
                    "description": row.get("description", "")
                }
                
                self._data[plate] = RegistryRecord(
                    plate_number=plate,
                    status=status,
                    flags=flags,
                    owner_info=owner_info
                )
        self._connected = True

    def lookup(self, plate_number: str) -> Optional[RegistryRecord]:
        if not self._connected:
            raise RuntimeError("Registry not connected. Call connect() first.")
        
        # Clean plate number just in case
        clean_plate = plate_number.strip().upper()
        return self._data.get(clean_plate)

    def fuzzy_lookup(self, plate_number: str, threshold: float = 0.85) -> Optional[RegistryRecord]:
        if not self._connected:
            raise RuntimeError("Registry not connected. Call connect() first.")
        
        clean_plate = plate_number.strip().upper()
        
        # Fast path: strict match
        if clean_plate in self._data:
            return self._data[clean_plate]
            
        # Slow path: difflib fuzzy match against all loaded records
        best_match = None
        best_ratio = 0.0
        
        for plate, record in self._data.items():
            ratio = difflib.SequenceMatcher(None, clean_plate, plate).ratio()
            if ratio > best_ratio and ratio >= threshold:
                best_ratio = ratio
                best_match = record
                
        return best_match
