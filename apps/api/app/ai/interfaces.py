from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from app.models import DecisionType, SourceCitation


@dataclass(frozen=True)
class AnalysisProviderRequest:
    project_description: str
    district: str
    citation_excerpts: list[str]
    missing_fields: list[str]


@dataclass(frozen=True)
class AnalysisProviderResult:
    decision: DecisionType
    summary: str
    required_permits: list[str] = field(default_factory=list)
    follow_up_questions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RetrievalProviderRequest:
    district: str
    inferred_use: str
    project_description: str = ""

    @property
    def query(self) -> str:
        return f"{self.inferred_use} {self.district} {self.project_description}".strip()


@dataclass(frozen=True)
class RetrievalProviderResult:
    citations: list[SourceCitation]


class AnalysisProvider(Protocol):
    name: str

    def generate_analysis(self, request: AnalysisProviderRequest) -> AnalysisProviderResult:
        """Generate structured zoning analysis from retrieved evidence."""


class RetrievalProvider(Protocol):
    name: str

    def retrieve(self, request: RetrievalProviderRequest) -> RetrievalProviderResult:
        """Retrieve zoning evidence for the project and jurisdiction context."""
