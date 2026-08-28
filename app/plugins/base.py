from abc import ABC, abstractmethod
from typing import Any, Dict

class BaseAnalyzerPlugin(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        """The distinct name of the plugin, matching keys in the final AnalyzeResponse context."""
        pass

    @abstractmethod
    def analyze(self, repo_path: str, context: Dict[str, Any]) -> Any:
        """Execute logic against repo_path and optionally read dependency properties from context."""
        pass
