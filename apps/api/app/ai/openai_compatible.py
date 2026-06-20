from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from app.ai.interfaces import AnalysisProviderRequest, AnalysisProviderResult
from app.ai.openai_provider import _post_with_retry


# Single source of truth for the zoning analysis prompt shared by every
# OpenAI-compatible analysis provider (Groq, Cerebras, OpenRouter). Keeping one
# canonical prompt prevents the per-provider drift that previously made
# different providers disagree on the same input.
ANALYSIS_SYSTEM_PROMPT = (
    "You are a zoning compliance assistant. Given a project description and "
    "citation excerpts from a jurisdiction's zoning ordinance, produce a JSON "
    "zoning analysis. Reason ONLY from the supplied excerpts — never from prior "
    "knowledge of this or any other jurisdiction, and never invent ordinance "
    "text, section numbers, districts, or use categories that are not present "
    "in the excerpts. Commit to a specific decision; use 'unknown' only in the "
    "cases described below.\n\n"
    "STEP 0 — UNLISTED USE (check first; overrides every step below). "
    "Determine whether the proposed use is covered by the excerpts at all. A "
    "use is COVERED when a provision in the excerpts — a permitted-use table "
    "row, a use definition, or a use-classification provision — names it or "
    "plainly and uncontroversially covers it (e.g. a clothing shop is a "
    "'retail' use; an apartment building is 'multifamily residential'; a use "
    "the ordinance expressly classifies under an industrial or other category "
    "is covered by that classification). A use is UNLISTED only when NO "
    "provision in the excerpts names, defines, or classifies it, so that "
    "assigning it to any category would require asserting it is 'substantially "
    "similar to' a listed use. That similar-use determination may be made only "
    "by the jurisdiction, never by you. For an UNLISTED use, set "
    "unlisted_use_determination to true, set decision to 'unknown', and stop. "
    "Otherwise set unlisted_use_determination to false and continue.\n\n"
    "STEP 1 — IDENTIFY the proposed principal use and the zoning district. If "
    "the 'district' field is 'unknown', infer the district from the "
    "project_description (a named district, or a phrase such as 'residential "
    "subdivision' or 'commercial corridor'), mapping it to a district code "
    "using ONLY the district definitions in the excerpts. When the request "
    "names a district by CATEGORY or type (e.g. 'a residential subdivision', "
    "'a commercial corridor') rather than an exact code, you need NOT pin the "
    "exact district: if the permitted-use table gives the proposed use the "
    "SAME status across every district of that category, decide from that "
    "shared status. Return 'unknown' for the district only when the use's "
    "status genuinely differs among the plausible districts AND the request "
    "gives you no basis to choose between them, or when no district (named or "
    "by category) can be inferred at all.\n\n"
    "STEP 2 — CLASSIFY the use for that district from the excerpts and choose "
    "the FIRST decision that applies. A use's permitted status is "
    "DISTRICT-SPECIFIC: a by-right or conditional permission applies ONLY to "
    "the districts the table explicitly lists for that status. Do NOT carry a "
    "status the table grants only to other districts over to the identified "
    "district. If the identified district is absent from every list of "
    "districts where the use is permitted (by right or conditionally), the use "
    "is restricted there.\n"
    "  • likely_allowed — the excerpts permit the use by right in that "
    "district with no additional approval named.\n"
    "  • conditional — the permitted-use table lists the IDENTIFIED district "
    "itself (not merely some other district) as one where the use is allowed "
    "subject to additional use regulations, conditions, or discretionary "
    "approval (special or conditional use, site-plan, or planning-commission / "
    "board review). A permission or condition that the table grants only in a "
    "DIFFERENT district does NOT make the use conditional in the identified "
    "district — that case is 'restricted' below. Name the controlling "
    "provision from the excerpts in the summary and list the required "
    "permits.\n"
    "  • restricted — the use is addressed by the excerpts (listed or "
    "classified) but is NOT permitted in the identified district: the "
    "permitted-use table does not allow it there, or the district's purpose / "
    "permitted-use provisions exclude the use's category (e.g. a use the "
    "excerpts classify as industrial in a district the excerpts reserve for "
    "residential use), or a provision naming THIS use imposes a requirement "
    "the district plainly cannot satisfy.\n"
    "  • unknown — the excerpts do not let you decide: the use is covered but "
    "the table gives no status for the identified district, the district "
    "cannot be determined, or the excerpts contain no permitted-use "
    "information for the use. Do not guess. (Genuinely unlisted uses are "
    "already handled by STEP 0.)\n\n"
    "Cite provisions only by the identifiers that actually appear in the "
    "excerpts; never cite a section that is not in the excerpts.\n\n"
    "Output JSON with these fields: decision, summary, "
    "required_permits (array), follow_up_questions (array), "
    "warnings (array), unlisted_use_determination (boolean)."
)

# Subsection 5.1.1.C invariant message attached when the model flags an unlisted use.
_UNLISTED_USE_WARNING = (
    "The proposed use is not a listed principal use in the permitted-use table; "
    "classifying it requires a Subsection 5.1.1.C similar-use determination made "
    "only by the jurisdiction, so no zoning conclusion can be drawn here."
)


def build_analysis_messages(request: AnalysisProviderRequest) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": ANALYSIS_SYSTEM_PROMPT},
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
    ]


def parse_analysis_payload(payload: dict[str, Any]) -> AnalysisProviderResult:
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
        warnings.append(_UNLISTED_USE_WARNING)
    return AnalysisProviderResult(
        decision=decision,
        summary=result["summary"],
        required_permits=list(result.get("required_permits", [])),
        follow_up_questions=list(result.get("follow_up_questions", [])),
        warnings=warnings,
    )


class OpenAICompatibleAnalysisProvider:
    """Generic analysis provider for any OpenAI-compatible chat-completions endpoint.

    Groq, Cerebras, and OpenRouter all expose the same `/chat/completions` shape,
    so they share this one implementation (and the one canonical prompt above).
    """

    def __init__(
        self,
        *,
        name: str,
        base_url: str,
        api_key: str,
        model: str,
        timeout: float,
        extra_retry_statuses: frozenset[int] = frozenset({429}),
        max_attempts: int = 6,
        extra_headers: Mapping[str, str] | None = None,
    ) -> None:
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.extra_retry_statuses = extra_retry_statuses
        self.max_attempts = max_attempts
        self.extra_headers = dict(extra_headers or {})

    def generate_analysis(self, request: AnalysisProviderRequest) -> AnalysisProviderResult:
        if not self.api_key:
            raise RuntimeError(f"{self.name}: missing API key")
        payload = _post_with_retry(
            url=f"{self.base_url}/chat/completions",
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                **self.extra_headers,
            },
            extra_retry_statuses=set(self.extra_retry_statuses),
            max_attempts=self.max_attempts,
            body={
                "model": self.model,
                "messages": build_analysis_messages(request),
                "response_format": {"type": "json_object"},
                "temperature": 0,
            },
            timeout=self.timeout,
        )
        return parse_analysis_payload(payload)
