from __future__ import annotations

from app.models import CitationValidationResult, SourceCitation
from app.jurisdictions import source_applies_to_jurisdiction
from app.repositories import StoreRepository


class CitationTool:
    def __init__(self, source_store: StoreRepository | None = None) -> None:
        self.source_store = source_store

    def validate(
        self,
        *,
        citations: list[SourceCitation],
        jurisdiction_id: str | None,
    ) -> CitationValidationResult:
        warnings: list[str] = []
        unsupported_claims: list[str] = []
        invalid_ids: list[str] = []

        if not citations:
            unsupported_claims.append("No retrieved source chunks are available for this analysis.")

        known_sources = self._known_sources()
        for citation in citations:
            if not citation.source_id:
                invalid_ids.append("<missing>")
                continue
            if known_sources and citation.source_id not in known_sources:
                invalid_ids.append(citation.source_id)
                unsupported_claims.append(f"{citation.source_id} was not found in the local source registry.")
            source = known_sources.get(citation.source_id)
            source_jurisdiction = source.jurisdiction_id if source else citation.jurisdiction_id
            source_metadata = source.metadata if source else citation.metadata
            if (
                jurisdiction_id
                and not source_applies_to_jurisdiction(
                    source_jurisdiction_id=source_jurisdiction,
                    source_metadata=source_metadata,
                    target_jurisdiction_id=jurisdiction_id,
                )
            ):
                invalid_ids.append(citation.source_id)
                unsupported_claims.append(
                    f"{citation.source_id} belongs to {source_jurisdiction or 'an unknown jurisdiction'}, not {jurisdiction_id}."
                )
            if not citation.effective_date:
                warnings.append(f"{citation.source_id} is missing an effective date.")

        invalid_ids = list(dict.fromkeys(invalid_ids))
        unsupported_claims = list(dict.fromkeys(unsupported_claims))
        valid = not invalid_ids and not unsupported_claims
        coverage = 1.0 if citations and valid else 0.0
        return CitationValidationResult(
            valid=valid,
            citation_coverage=coverage,
            unsupported_claims=unsupported_claims,
            invalid_citation_ids=invalid_ids,
            confidence_adjustment="none" if valid else "downgrade_low_confidence",
            warnings=warnings,
            jurisdiction_id=jurisdiction_id,
        )

    def _known_sources(self):
        if not self.source_store:
            return {}
        return {
            source.source_id: source
            for source in self.source_store.list_sources()
        }
