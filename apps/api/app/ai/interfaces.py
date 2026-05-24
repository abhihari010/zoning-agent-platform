from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from app.models import ComplianceResult, DecisionType, SourceCitation

if TYPE_CHECKING:
    from app.models import RetrievalDiagnostics, SourceChunk


@dataclass(frozen=True)
class AnalysisProviderRequest:
    project_description: str
    district: str
    citation_excerpts: list[str]
    missing_fields: list[str]
    chunks: list["SourceChunk"] = field(default_factory=list)
    inferred_use: str = "general"


@dataclass(frozen=True)
class AnalysisProviderResult:
    decision: DecisionType
    summary: str
    required_permits: list[str] = field(default_factory=list)
    follow_up_questions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    compliance: ComplianceResult | None = None


@dataclass(frozen=True)
class RetrievalProviderRequest:
    district: str
    inferred_use: str
    project_description: str = ""
    jurisdiction_id: str | None = None

    @property
    def query(self) -> str:
        return f"{self.inferred_use} {self.district} {self.project_description}".strip()


@dataclass(frozen=True)
class RetrievalProviderResult:
    citations: list[SourceCitation]
    chunks: list["SourceChunk"] = field(default_factory=list)
    # Optional diagnostics populated by hybrid_local provider.
    diagnostics: "RetrievalDiagnostics | None" = None


@dataclass(frozen=True)
class EmbeddingProviderRequest:
    texts: list[str]


@dataclass(frozen=True)
class EmbeddingProviderResult:
    embeddings: list[list[float]]


class AnalysisProvider(Protocol):
    name: str

    def generate_analysis(self, request: AnalysisProviderRequest) -> AnalysisProviderResult:
        """Generate structured zoning analysis from retrieved evidence."""


class RetrievalProvider(Protocol):
    name: str

    def retrieve(self, request: RetrievalProviderRequest) -> RetrievalProviderResult:
        """Retrieve zoning evidence for the project and jurisdiction context."""


class EmbeddingProvider(Protocol):
    name: str

    def embed(self, request: EmbeddingProviderRequest) -> EmbeddingProviderResult:
        """Return vector embeddings for text input, or an empty list when disabled."""
