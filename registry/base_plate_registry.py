"""
Abstract interface for plate registry lookups.

Any concrete registry (mock MySQL-seeded table, or the future real
VAHAN/eGujCop API client) must implement this contract so the rule
engine can look up a plate's status without caring whether the data
came from a local mock table or a live government API.
"""

from abc import ABC, abstractmethod
from typing import Any, Optional


class RegistryRecord:
    """
    Container for a plate registry lookup result.

    Attributes:
        plate_number: The plate string that was looked up.
        status:       e.g. "clear", "stolen", "flagged", "unregistered".
        flags:        List of specific flag strings (e.g. ["expired_insurance"]).
        owner_info:   Optional dict with additional owner/vehicle details,
                      when available and permitted.
    """

    def __init__(
        self,
        plate_number: str,
        status: str,
        flags: Optional[list[str]] = None,
        owner_info: Optional[dict[str, Any]] = None,
    ):
        self.plate_number = plate_number
        self.status = status
        self.flags = flags or []
        self.owner_info = owner_info or {}

    def __repr__(self) -> str:
        return (
            f"RegistryRecord(plate_number='{self.plate_number}', "
            f"status='{self.status}', flags={self.flags})"
        )


class BasePlateRegistry(ABC):
    """
    Contract for any plate registry lookup source.

    Usage:
        registry = SomeConcreteRegistry()
        record = registry.lookup("GJ01AB1234")
        if record is not None and record.status != "clear":
            # raise an alert
            ...
    """

    @abstractmethod
    def lookup(self, plate_number: str) -> Optional[RegistryRecord]:
        """
        Look up a plate number against the registry.

        Args:
            plate_number: The (OCR-read, possibly noisy) plate string.

        Returns:
            A RegistryRecord if the plate is found, or None if the
            plate has no matching record at all (distinct from a
            record with status="unregistered", which means it was
            found but explicitly marked unregistered).
        """
        raise NotImplementedError

    def fuzzy_lookup(self, plate_number: str, threshold: float = 0.85) -> Optional[RegistryRecord]:
        """
        Fuzzy match a plate number against the registry (e.g. using difflib).
        Useful for catching OCR misreads like '8' vs 'B'.
        """
        # Default fallback is strict lookup
        return self.lookup(plate_number)

    @abstractmethod
    def connect(self) -> None:
        """
        Establish the connection to the underlying registry source
        (e.g. open a DB connection or authenticate against an API).
        """
        raise NotImplementedError
