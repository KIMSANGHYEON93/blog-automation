"""SEO Ports — Domain interfaces for indexing and CWV checks."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class IndexingResult:
    """URL indexing status result."""

    url: str
    is_indexed: bool = False
    verdict: str = ""
    coverage_state: str = ""
    indexing_state: str = ""
    robots_txt_state: str = ""
    last_crawl_time: str = ""
    error: str = ""


@dataclass(frozen=True)
class CwvResult:
    """Core Web Vitals measurement result."""

    lcp_seconds: float = 0.0
    cls_score: float = 0.0
    performance_score: int = 0
    passed: bool = False
    error: str = ""


class IndexingPort(ABC):
    @abstractmethod
    def check(self, url: str) -> IndexingResult: ...


class CwvPort(ABC):
    @abstractmethod
    def check(self, url: str) -> CwvResult: ...
