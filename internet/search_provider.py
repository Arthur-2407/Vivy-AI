"""
Vivy AI — Internet Intelligence Layer: Search Provider Abstract Interface
Provides a unified contract for all search engine adapters (DuckDuckGo, Wikipedia, Google, Bing, etc.)
"""

from dataclasses import dataclass, field
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import time

@dataclass
class SearchResult:
    """Standardized Search Result payload across all providers."""
    title: str
    snippet: str
    url: str = ""
    source: str = "unknown"
    timestamp: float = field(default_factory=time.time)
    confidence: float = 1.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "title": self.title,
            "snippet": self.snippet,
            "url": self.url,
            "source": self.source,
            "timestamp": self.timestamp,
            "confidence": self.confidence,
            "metadata": self.metadata
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SearchResult":
        return cls(
            title=data.get("title", ""),
            snippet=data.get("snippet", ""),
            url=data.get("url", ""),
            source=data.get("source", "unknown"),
            timestamp=data.get("timestamp", time.time()),
            confidence=data.get("confidence", 1.0),
            metadata=data.get("metadata", {})
        )

    def to_formatted_snippet(self) -> str:
        """Returns clean markdown snippet for prompt injection."""
        if self.title:
            return f"- **{self.title}**: {self.snippet}"
        return f"- {self.snippet}"


class SearchProvider(ABC):
    """Abstract Base Class for all internet search adapters."""

    @abstractmethod
    def name(self) -> str:
        """Return unique provider identifier."""
        pass

    @abstractmethod
    def is_available(self) -> bool:
        """Return True if provider dependencies and configuration are ready."""
        pass

    @abstractmethod
    def search(self, query: str, max_results: int = 5, **kwargs) -> List[SearchResult]:
        """
        Execute search query and return standardized list of SearchResult objects.
        Must handle exceptions gracefully and return empty list on failure.
        """
        pass
