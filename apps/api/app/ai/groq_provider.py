from __future__ import annotations

import json

from app.ai.interfaces import AnalysisProviderRequest, AnalysisProviderResult
from app.ai.openai_provider import _post_with_retry
from app.settings import get_settings

GROQ_BASE_URL = "https://api.groq.com/openai/v1"


class GroqAnalysisProvider:
    name = "groq"

    def generate_analysis(self, request: AnalysisProviderRequest) -> AnalysisProviderResult:
        settings = get_settings()
        payload = _post_with_retry(
            url=f"{GROQ_BASE_URL}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.groq_api_key}",
                "Content-Type": "application/json",
            },
            # Groq free-tier hits 429s on per-minute limits; retry with backoff
            # so the deterministic fallback isn't silently engaged on transient limits.
            extra_retry_statuses={429},
            max_attempts=6,
            body={
                "model": settings.groq_model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            "You are a zoning compliance assistant. Given a project description "
                            "and citation excerpts, output a JSON zoning analysis. You MUST commit "
                            "to a specific decision — only use 'unknown' in the cases described "
                            "under RULE 0 and RULE 4.\n\n"
                            "RULE 0 — unlisted use (CHECK THIS FIRST; overrides every rule below): "
                            "If the proposed use is not a use type that the permitted-use table "
                            "(Subsection 5.1.3) actually lists or plainly covers — i.e. assigning it "
                            "to a row would require asserting it is 'substantially similar to' some "
                            "listed use — then it is an UNLISTED use. Per Subsection 5.1.1.C only "
                            "the jurisdiction may make that similar-use determination, never you. "
                            "Specialized production uses that are not named, such as a brewery, "
                            "distillery, or winery (even one with an on-site taproom), are unlisted; "
                            "do NOT reclassify them as an industrial use, a restaurant, or any other "
                            "listed use. For an unlisted use, set unlisted_use_determination to true "
                            "and decision to 'unknown' and stop. For every other use, set "
                            "unlisted_use_determination to false and apply the rules below.\n\n"
                            "DISTRICT: Read the project_description text to find the district "
                            "(ignore the 'district' field if it says 'unknown'). "
                            "R1/R2/R3/R4 or 'residential neighborhood/subdivision' = residential. "
                            "Downtown District, Central Commercial (CC), Neighborhood Commercial "
                            "(NC), Regional Commercial (RC4), or 'commercial district/corridor' "
                            "= commercial.\n\n"
                            "Apply the FIRST rule that matches:\n\n"
                            "RULE 1 — likely_allowed: the proposed use is a CHARACTERISTIC use "
                            "of this district AND no §5.1.4 subsection in the excerpts explicitly "
                            "names THIS specific use type with conditions.\n"
                            "  • Any single-family home or dwelling in an R-zone → likely_allowed "
                            "(unless §5.1.4 explicitly names this use — SFR in R-zones has no "
                            "§5.1.4 condition, so commit here).\n"
                            "  • Restaurant or retail store in Downtown, CC, NC, or commercial "
                            "district → likely_allowed (unless §5.1.4 explicitly names this use "
                            "type — §5.1.4.G names 'Event Venues', NOT restaurants; §5.1.4.I "
                            "names 'Gas Stations', NOT general retail; do not apply other-use "
                            "§5.1.4 sections to a restaurant or retail shop).\n"
                            "  COMMIT to likely_allowed when these examples match. "
                            "Principal-use alignment with the district purpose is sufficient.\n\n"
                            "RULE 2 — conditional: a §5.1.4 subsection or Chapter 20 / §20.12 "
                            "provision in the excerpts explicitly names THIS specific use type "
                            "(not a different use) as requiring conditions or planning-commission "
                            "approval. Short-term vacation rentals (§5.1.4.W), gas stations "
                            "(§5.1.4.I + §20.12.2.C.9), event venues (§5.1.4.G + §20.12.2.C.8), "
                            "and multifamily with ground-floor commercial requirement (§5.1.4.R) "
                            "are examples. Name the provision in your summary.\n\n"
                            "RULE 3 — restricted:\n"
                            "  (a) The use is INDUSTRIAL (manufacturing, assembly, vehicle repair, "
                            "self-storage, vape shops — identified by appearing under an "
                            "INDUSTRIAL USES section header in §5.1.3) AND the district is "
                            "RESIDENTIAL (R1-R4). Residential district purpose text excluding "
                            "non-residential uses is sufficient; no use-table dot needed.\n"
                            "  (b) §5.1.4 explicitly names THIS use type with a setback from "
                            "residential property (e.g., 500 ft from dwellings), AND the district "
                            "is Neighborhood Commercial or otherwise described as serving "
                            "surrounding residential neighborhoods — making compliance with that "
                            "setback practically impossible at the NC site.\n\n"
                            "RULE 4 — unknown (LAST RESORT only): the use is INDUSTRIAL "
                            "(per §5.2.7 or §5.1.3 industrial section) AND the district is "
                            "COMMERCIAL (not residential), AND §5.1.4 does NOT name this specific "
                            "use — so whether commercial districts permit this industrial use "
                            "cannot be determined from the text corpus. "
                            "Do NOT use 'unknown' for residential uses in R-zones, commercial "
                            "uses in commercial zones, or any use that §5.1.4 explicitly names "
                            "(those go to rule 2 or rule 3).\n\n"
                            "Output JSON with these fields: decision, summary, "
                            "required_permits (array), follow_up_questions (array), "
                            "warnings (array), unlisted_use_determination (boolean)."
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "project_description": request.project_description,
                                "district": request.district,
                                "citation_excerpts": request.citation_excerpts,
                                "missing_fields": request.missing_fields,
                            }
                        ),
                    },
                ],
                "response_format": {"type": "json_object"},
                "temperature": 0,
            },
            timeout=settings.groq_timeout_seconds,
        )
        content = payload["choices"][0]["message"]["content"]
        result = json.loads(content)
        decision = result["decision"]
        warnings = list(result.get("warnings", []))
        # Enforce the Subsection 5.1.1.C invariant structurally: an unlisted use cannot be
        # classified by reclassifying it under a broader row (a similar-use determination only
        # the jurisdiction may make). If the model flags the use as unlisted, the honest answer
        # is unknown regardless of any rule it may have otherwise applied.
        if bool(result.get("unlisted_use_determination", False)) and decision != "unknown":
            decision = "unknown"
            warnings.append(
                "The proposed use is not a listed principal use in the permitted-use table; "
                "classifying it requires a Subsection 5.1.1.C similar-use determination made "
                "only by the jurisdiction, so no zoning conclusion can be drawn here."
            )
        return AnalysisProviderResult(
            decision=decision,
            summary=result["summary"],
            required_permits=list(result.get("required_permits", [])),
            follow_up_questions=list(result.get("follow_up_questions", [])),
            warnings=warnings,
        )
