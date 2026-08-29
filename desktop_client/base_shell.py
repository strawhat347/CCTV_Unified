"""
Abstract base class for a Desktop Client shell.
Defines the required interface so we can swap between PyWebView and Electron.
"""
from abc import ABC, abstractmethod

class BaseShell(ABC):
    @abstractmethod
    def launch(self, frontend_path: str, api_base_url: str) -> None:
        """
        Launch the desktop window pointing to the given frontend directory
        and configure it to hit the target API backend.
        """
        pass
