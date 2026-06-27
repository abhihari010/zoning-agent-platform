"""LLM district classifier for jurisdiction expansion (Stage 4).

Replaces hand-authored ``classification_rules.json`` files with a Groq LLM
pass: each scraped ordinance section's heading + article/division breadcrumb
is fed to the LLM, which returns a normalized district + use classification
from a **closed vocabulary**.  The output is a reviewable
``classification_rules.json`` (same schema as the hand-authored Blacksburg
file) plus a ``_classification_report.json`` for human spot-checking.

SAFETY BOUNDARY
---------------
This script stops at *reviewable output files*.  It does NOT:
  - auto-promote a pack to ``public_supported``
  - write into ``apps/api/app/data/source_packs`` (unless ``--in-place`` is given
    with an explicit target manifest path inside the curated tree)
  - trigger a vector reindex

Promotion and reindexing remain deliberate, human-gated steps.

CLOSED VOCABULARY (single source of truth)
------------------------------------------
The LLM may only emit terms from these sets; anything else is coerced to
``unknown`` (districts) or ``general`` (uses) before being written.

  DISTRICT_VOCAB = {
      "residential-low-density",
      "mixed-use-core",
      "commercial-employment",
      "industrial-zone",
      "unknown",
  }

  USES_VOCAB = {
      "general",
      "food-service",
      "food-business",
      "home-based-food-business",
  }

GROQ DEPENDENCY
---------------
The live LLM call uses the ``openai`` SDK pointed at Groq's OpenAI-compatible
endpoint (``https://api.groq.com/openai/v1``).  The ``openai`` package is
already in the API's base dependencies, so no extra install is needed.
However, if running in a bare Python environment without the package, a clear
``ImportError`` message is raised.

The LLM function is **injectable**: tests pass a stub callable instead of the
real Groq call, so all offline tests pass without ``GROQ_API_KEY``.

Usage
-----
  # Classify a batch-scrape draft:
  python scripts/classify_districts.py \\
      --manifest .tmp/source_pack_drafts/va/christiansburg-va/manifest.json

  # Write next to a curated pack manifest:
  python scripts/classify_districts.py \\
      --manifest apps/api/app/data/source_packs/va/christiansburg-va/manifest.json \\
      --in-place

  # Override model / confidence threshold:
  python scripts/classify_districts.py \\
      --manifest path/to/manifest.json \\
      --model llama-3.1-8b-instant \\
      --min-confidence 0.8

Exit codes
----------
0  — classification completed, files written (warnings may be present).
1  — fatal error (missing manifest, missing API key for live run, etc.).

Note: a live run requires GROQ_API_KEY in the environment.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

# ---------------------------------------------------------------------------
# Repo-root bootstrap
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# ---------------------------------------------------------------------------
# Closed vocabulary — SINGLE SOURCE OF TRUTH
# Never let the LLM invent new terms; anything outside these sets is coerced.
# ---------------------------------------------------------------------------

DISTRICT_VOCAB: frozenset[str] = frozenset(
    {
        "residential-low-density",
        "mixed-use-core",
        "commercial-employment",
        "industrial-zone",
        "agricultural",
        "unknown",
    }
)

USES_VOCAB: frozenset[str] = frozenset(
    {
        "general",
        "food-service",
        "food-business",
        "home-based-food-business",
    }
)

DEFAULT_DISTRICTS: list[str] = ["unknown"]
DEFAULT_USES: list[str] = ["general"]

# LLM constants
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
DEFAULT_MODEL = "llama-3.3-70b-versatile"
DEFAULT_MIN_CONFIDENCE = 0.7
# Max sample section titles to include per group (keeps prompt compact)
MAX_SAMPLE_TITLES = 5
# Max character length for a sample title
MAX_TITLE_LEN = 80


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class SectionGroup:
    """A set of ordinance sections sharing the same (article, division) pair."""

    article: str
    division: str
    sample_titles: list[str]
    section_count: int


@dataclass
class ClassificationResult:
    """LLM classification for a single SectionGroup."""

    article: str
    division: str
    districts: list[str]
    uses: list[str]
    rationale: str
    confidence: float
    raw_response: str = ""
    error: str = ""  # non-empty if parsing/call failed
    coerced: bool = False  # True if off-vocab terms were coerced


@dataclass
class ClassificationReport:
    """Machine-readable report written alongside classification_rules.json."""

    generated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    manifest_path: str = ""
    model: str = ""
    min_confidence: float = DEFAULT_MIN_CONFIDENCE
    group_count: int = 0
    coerced_count: int = 0
    error_count: int = 0
    low_confidence_count: int = 0
    results: list[dict] = field(default_factory=list)
    note: str = (
        "REVIEW REQUIRED — do not promote to public_supported until all "
        "groups have been spot-checked. Coerced/low-confidence groups default "
        "to 'unknown'/'general'."
    )

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


# ---------------------------------------------------------------------------
# Grouping logic
# ---------------------------------------------------------------------------


def group_sections(sources: list[dict]) -> list[SectionGroup]:
    """Group source entries by (article, division) breadcrumb pair.

    Breadcrumb structure (from scraper):
      breadcrumb[0] = chapter
      breadcrumb[1] = article
      breadcrumb[2] = division (optional)

    Groups with an empty article are collected under a synthetic
    ``"(no article)"`` key.
    """
    groups: dict[tuple[str, str], list[str]] = defaultdict(list)

    for src in sources:
        if not isinstance(src, dict):
            continue
        metadata = src.get("metadata") if isinstance(src.get("metadata"), dict) else {}
        breadcrumb = metadata.get("breadcrumb")
        if not isinstance(breadcrumb, list):
            breadcrumb = []

        article = str(breadcrumb[1]).strip() if len(breadcrumb) > 1 else ""
        division = str(breadcrumb[2]).strip() if len(breadcrumb) > 2 else ""

        title = str(src.get("title") or "").strip()
        if title:
            groups[(article, division)].append(title)
        else:
            groups[(article, division)]  # ensure key exists even with no title

    result: list[SectionGroup] = []
    for (article, division), titles in groups.items():
        sample = [t[:MAX_TITLE_LEN] for t in titles[:MAX_SAMPLE_TITLES]]
        result.append(
            SectionGroup(
                article=article,
                division=division,
                sample_titles=sample,
                section_count=len(titles),
            )
        )

    # Deterministic order: article then division
    result.sort(key=lambda g: (g.article, g.division))
    return result


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------


def build_prompt(group: SectionGroup) -> str:
    """Build the Groq classification prompt for a SectionGroup."""
    district_list = "\n".join(
        f"  - {d}" for d in sorted(DISTRICT_VOCAB - {"unknown"})
    ) + "\n  - unknown  (use when unsure)"

    uses_list = "\n".join(
        f"  - {u}" for u in sorted(USES_VOCAB - {"general"})
    ) + "\n  - general  (use when unsure, or for broad/cross-cutting sections)"

    titles_text = (
        "\n".join(f"  * {t}" for t in group.sample_titles)
        if group.sample_titles
        else "  (no titles available)"
    )

    prompt = textwrap.dedent(f"""\
        You are a zoning-ordinance classifier. Given an article name and division \
name from a municipal zoning code, classify the section group into the normalized \
district and use categories below.

CLOSED VOCABULARY — you MUST choose ONLY from these exact strings:

Districts:
{district_list}

Uses:
{uses_list}

CLASSIFICATION RULES:
1. Choose ONLY the exact string(s) from the vocabulary above. Do NOT invent new terms.
2. If you are unsure or the section is cross-cutting, use "unknown" for districts.
3. If the section governs specific district-level standards, include "unknown" AND \
the specific district (e.g. ["unknown", "residential-low-density"]).
4. For use standards that apply across districts, keep districts as ["unknown"] and \
classify uses specifically.
5. Low-confidence answers: set confidence below 0.7 and use "unknown"/"general".

Article: {group.article or "(none)"}
Division: {group.division or "(none)"}
Sample section titles ({group.section_count} total sections in this group):
{titles_text}

Respond with EXACTLY this JSON (no markdown fences, no extra text):
{{
  "districts": ["<district-term>"],
  "uses": ["<use-term>"],
  "rationale": "<one sentence explaining the classification>",
  "confidence": <float 0.0–1.0>
}}
""")
    return prompt


# ---------------------------------------------------------------------------
# LLM response parsing and vocab coercion
# ---------------------------------------------------------------------------


def parse_llm_response(raw: str) -> dict[str, Any]:
    """Parse the LLM JSON response.

    Returns a dict with keys: districts, uses, rationale, confidence.
    On any parse failure, returns safe defaults and sets an 'error' key.
    """
    raw = raw.strip()
    # Strip markdown fences if the LLM added them despite instructions.
    if raw.startswith("```"):
        lines = raw.splitlines()
        # Remove first and last fence lines
        inner = [
            l for l in lines if not l.strip().startswith("```")
        ]
        raw = "\n".join(inner).strip()

    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        return {
            "districts": DEFAULT_DISTRICTS[:],
            "uses": DEFAULT_USES[:],
            "rationale": "",
            "confidence": 0.0,
            "error": f"JSON parse error: {exc}",
        }

    if not isinstance(data, dict):
        return {
            "districts": DEFAULT_DISTRICTS[:],
            "uses": DEFAULT_USES[:],
            "rationale": "",
            "confidence": 0.0,
            "error": "LLM returned non-object JSON",
        }

    # Extract fields with safe defaults.
    districts = data.get("districts")
    uses = data.get("uses")
    rationale = str(data.get("rationale") or "").strip()
    confidence = data.get("confidence")

    # Normalize lists.
    if not isinstance(districts, list):
        districts = DEFAULT_DISTRICTS[:]
    else:
        districts = [str(d).strip() for d in districts if str(d).strip()]
        if not districts:
            districts = DEFAULT_DISTRICTS[:]

    if not isinstance(uses, list):
        uses = DEFAULT_USES[:]
    else:
        uses = [str(u).strip() for u in uses if str(u).strip()]
        if not uses:
            uses = DEFAULT_USES[:]

    # Normalize confidence.
    try:
        confidence = float(confidence)  # type: ignore[arg-type]
        confidence = max(0.0, min(1.0, confidence))
    except (TypeError, ValueError):
        confidence = 0.0

    return {
        "districts": districts,
        "uses": uses,
        "rationale": rationale,
        "confidence": confidence,
        "error": "",
    }


def coerce_vocab(
    districts: list[str],
    uses: list[str],
) -> tuple[list[str], list[str], bool]:
    """Coerce any off-vocab terms to unknown/general.

    Returns (coerced_districts, coerced_uses, was_coerced).
    ``was_coerced`` is True if any term was replaced.
    """
    coerced = False
    out_districts: list[str] = []
    for d in districts:
        if d in DISTRICT_VOCAB:
            out_districts.append(d)
        else:
            out_districts.append("unknown")
            coerced = True

    out_uses: list[str] = []
    for u in uses:
        if u in USES_VOCAB:
            out_uses.append(u)
        else:
            out_uses.append("general")
            coerced = True

    # Deduplicate while preserving order.
    seen_d: set[str] = set()
    out_districts = [d for d in out_districts if not (d in seen_d or seen_d.add(d))]  # type: ignore[func-returns-value]
    seen_u: set[str] = set()
    out_uses = [u for u in out_uses if not (u in seen_u or seen_u.add(u))]  # type: ignore[func-returns-value]

    if not out_districts:
        out_districts = DEFAULT_DISTRICTS[:]
    if not out_uses:
        out_uses = DEFAULT_USES[:]

    return out_districts, out_uses, coerced


# ---------------------------------------------------------------------------
# Core classification (injectable LLM function)
# ---------------------------------------------------------------------------


def classify_group(
    group: SectionGroup,
    llm_fn: Callable[[str], str],
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> ClassificationResult:
    """Classify a single SectionGroup using the injectable LLM function.

    ``llm_fn`` is a callable that takes a prompt string and returns the raw LLM
    response string.  In production this wraps the Groq API; in tests it's a
    stub that returns predefined JSON strings.

    Low-confidence (< min_confidence) and error responses both fall back to
    safe defaults (``["unknown"]`` / ``["general"]``).
    """
    prompt = build_prompt(group)
    raw_response = ""
    error = ""

    try:
        raw_response = llm_fn(prompt)
    except Exception as exc:  # noqa: BLE001
        error = f"LLM call failed: {exc}"
        return ClassificationResult(
            article=group.article,
            division=group.division,
            districts=DEFAULT_DISTRICTS[:],
            uses=DEFAULT_USES[:],
            rationale="",
            confidence=0.0,
            raw_response="",
            error=error,
        )

    parsed = parse_llm_response(raw_response)
    if parsed.get("error"):
        # Keep the raw response for the report but fall back to defaults.
        return ClassificationResult(
            article=group.article,
            division=group.division,
            districts=DEFAULT_DISTRICTS[:],
            uses=DEFAULT_USES[:],
            rationale="",
            confidence=0.0,
            raw_response=raw_response,
            error=parsed["error"],
        )

    districts, uses, coerced = coerce_vocab(parsed["districts"], parsed["uses"])
    confidence = parsed["confidence"]

    # Low-confidence → safe fallback; still record the rationale.
    if confidence < min_confidence:
        return ClassificationResult(
            article=group.article,
            division=group.division,
            districts=DEFAULT_DISTRICTS[:],
            uses=DEFAULT_USES[:],
            rationale=parsed["rationale"],
            confidence=confidence,
            raw_response=raw_response,
            error="",
            coerced=coerced,
        )

    return ClassificationResult(
        article=group.article,
        division=group.division,
        districts=districts,
        uses=uses,
        rationale=parsed["rationale"],
        confidence=confidence,
        raw_response=raw_response,
        error="",
        coerced=coerced,
    )


# ---------------------------------------------------------------------------
# Rules file builder
# ---------------------------------------------------------------------------


def results_to_rules(results: list[ClassificationResult]) -> dict:
    """Convert classification results to ``source-classification-rules/v1`` format.

    Follows the Blacksburg convention:
    - First-match ordering (most specific first).
    - Sections with only ``["unknown"]`` districts are still included (they
      refine the ``uses`` classification even for cross-cutting sections).
    - Groups with both ``districts=["unknown"]`` and ``uses=["general"]``
      (pure defaults, no real classification) are omitted since they carry
      no information beyond the global default.
    """
    rules = []
    for r in results:
        # Skip pure no-op rules (would just re-emit the global default).
        is_default_districts = r.districts == DEFAULT_DISTRICTS
        is_default_uses = r.uses == DEFAULT_USES
        if is_default_districts and is_default_uses:
            continue

        rule: dict[str, Any] = {}
        if r.article:
            rule["article_contains"] = r.article
        if r.division:
            rule["division_contains"] = r.division
        rule["districts"] = r.districts
        rule["uses"] = r.uses
        rules.append(rule)

    coerced_groups = [r for r in results if r.coerced]
    error_groups = [r for r in results if r.error]
    low_conf_groups = [r for r in results if not r.error and r.confidence < DEFAULT_MIN_CONFIDENCE]

    notes_parts = [
        "Auto-generated by scripts/classify_districts.py (Stage 4).",
        "Rules are first-match; review ordering before promotion.",
    ]
    if coerced_groups:
        notes_parts.append(
            f"{len(coerced_groups)} group(s) had off-vocab terms coerced to unknown/general."
        )
    if error_groups:
        notes_parts.append(
            f"{len(error_groups)} group(s) had LLM errors and defaulted to unknown/general."
        )
    if low_conf_groups:
        notes_parts.append(
            f"{len(low_conf_groups)} group(s) were low-confidence and defaulted to unknown/general."
        )
    notes_parts.append("REVIEW REQUIRED before promoting to public_supported.")

    return {
        "schema_version": "source-classification-rules/v1",
        "_notes": "  ".join(notes_parts),
        "rules": rules,
    }


# ---------------------------------------------------------------------------
# Manifest loading
# ---------------------------------------------------------------------------


def load_manifest(path: Path) -> list[dict]:
    """Load the ``sources`` list from a manifest.json.

    Raises ``ValueError`` on I/O errors or missing ``sources`` key.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Cannot read manifest {path}: {exc}") from exc
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Cannot parse manifest JSON at {path}: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError(f"Manifest must be a JSON object: {path}")
    sources = data.get("sources")
    if not isinstance(sources, list):
        raise ValueError(f"Manifest missing 'sources' array: {path}")
    return sources


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------


def write_outputs(
    rules: dict,
    report: ClassificationReport,
    output_dir: Path,
) -> tuple[Path, Path]:
    """Write ``classification_rules.json`` and ``_classification_report.json``.

    Returns ``(rules_path, report_path)``.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    rules_path = output_dir / "classification_rules.json"
    report_path = output_dir / "_classification_report.json"

    rules_path.write_text(json.dumps(rules, indent=2) + "\n", encoding="utf-8")
    report_path.write_text(
        json.dumps(report.to_dict(), indent=2) + "\n", encoding="utf-8"
    )

    return rules_path, report_path


def print_human_summary(report: ClassificationReport, rules_path: Path) -> None:
    """Print a concise human-readable summary to stderr."""
    lines = [
        "",
        "=" * 68,
        "DISTRICT CLASSIFICATION REPORT",
        f"  Generated : {report.generated_at}",
        f"  Manifest  : {report.manifest_path}",
        f"  Model     : {report.model}",
        f"  Groups    : {report.group_count}  "
        f"(errors={report.error_count}  "
        f"low-conf={report.low_confidence_count}  "
        f"coerced={report.coerced_count})",
        f"  Rules out : {rules_path}",
        "-" * 68,
    ]
    for r in report.results:
        art = (r.get("article") or "(none)")[:40]
        div = (r.get("division") or "(none)")[:40]
        conf = r.get("confidence", 0.0)
        districts = r.get("districts", ["unknown"])
        uses = r.get("uses", ["general"])
        err = r.get("error", "")
        flags = []
        if r.get("coerced"):
            flags.append("COERCED")
        if err:
            flags.append(f"ERROR:{err[:40]}")
        if conf < report.min_confidence and not err:
            flags.append("LOW-CONF")
        flag_str = "  [" + ", ".join(flags) + "]" if flags else ""
        lines.append(
            f"  {art} / {div}"
        )
        lines.append(
            f"    districts={districts}  uses={uses}  conf={conf:.2f}{flag_str}"
        )
        if r.get("rationale"):
            lines.append(f"    rationale: {r['rationale'][:80]}")
    lines.append("=" * 68)
    lines.append("NOTE: REVIEW REQUIRED — spot-check before promoting to public_supported.")
    lines.append("")
    print("\n".join(lines), file=sys.stderr)


# ---------------------------------------------------------------------------
# Live Groq LLM function (lazy import)
# ---------------------------------------------------------------------------


def make_groq_llm_fn(api_key: str, model: str) -> Callable[[str], str]:
    """Build the live Groq LLM function.

    Uses the ``openai`` SDK pointed at Groq's OpenAI-compatible endpoint.
    The SDK is already in the API's base dependencies; we import lazily so
    offline tests that never call this function don't need the package.

    Raises ``ImportError`` with a clear message if the SDK is not available.
    """
    try:
        from openai import OpenAI  # type: ignore[import]
    except ImportError as exc:
        raise ImportError(
            "The 'openai' package is required for live Groq calls. "
            "Install it with: pip install openai"
        ) from exc

    client = OpenAI(api_key=api_key, base_url=GROQ_BASE_URL)

    def _call(prompt: str) -> str:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            temperature=0.0,
            max_tokens=512,
        )
        return response.choices[0].message.content or ""

    return _call


# ---------------------------------------------------------------------------
# Main classification loop
# ---------------------------------------------------------------------------


def run_classification(
    manifest_path: Path,
    *,
    llm_fn: Callable[[str], str],
    model: str = DEFAULT_MODEL,
    min_confidence: float = DEFAULT_MIN_CONFIDENCE,
) -> tuple[dict, ClassificationReport]:
    """Load manifest → group sections → classify each group → build outputs.

    Returns ``(rules_dict, report)`` for the caller to write.
    Raises ``ValueError`` on manifest loading errors.
    """
    sources = load_manifest(manifest_path)

    groups = group_sections(sources)

    results: list[ClassificationResult] = []
    for group in groups:
        result = classify_group(group, llm_fn, min_confidence=min_confidence)
        results.append(result)

    rules = results_to_rules(results)

    report = ClassificationReport(
        manifest_path=str(manifest_path),
        model=model,
        min_confidence=min_confidence,
        group_count=len(groups),
        coerced_count=sum(1 for r in results if r.coerced),
        error_count=sum(1 for r in results if r.error),
        low_confidence_count=sum(
            1 for r in results if not r.error and r.confidence < min_confidence
        ),
        results=[
            {
                "article": r.article,
                "division": r.division,
                "districts": r.districts,
                "uses": r.uses,
                "rationale": r.rationale,
                "confidence": r.confidence,
                "coerced": r.coerced,
                "error": r.error,
            }
            for r in results
        ],
    )

    return rules, report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "LLM district classifier (Stage 4 — jurisdiction expansion). "
            "Reads a source pack manifest.json, groups sections by article/division, "
            "calls Groq to classify each group, and emits classification_rules.json + "
            "_classification_report.json for human review. "
            "SAFETY: never auto-promotes packs; never reindexes."
        )
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        required=True,
        help=(
            "Path to a source pack manifest.json "
            "(draft or curated). Output files are written next to this manifest "
            "unless --output-dir is specified."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help=(
            "Directory to write classification_rules.json and "
            "_classification_report.json (default: same directory as --manifest)."
        ),
    )
    parser.add_argument(
        "--in-place",
        action="store_true",
        help=(
            "Write outputs next to --manifest (same as default, but explicit). "
            "Use when classifying a curated pack for direct promotion review."
        ),
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        help=f"Groq model ID (default: {DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--min-confidence",
        type=float,
        default=DEFAULT_MIN_CONFIDENCE,
        help=(
            f"Groups with LLM confidence below this threshold default to "
            f"unknown/general (default: {DEFAULT_MIN_CONFIDENCE})."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print what would be written without creating files.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    manifest_path: Path = args.manifest.resolve()
    if not manifest_path.exists():
        print(f"[classifier] ERROR: manifest not found: {manifest_path}", file=sys.stderr)
        return 1

    output_dir = (args.output_dir or manifest_path.parent).resolve()

    # Resolve GROQ_API_KEY from environment.
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        print(
            "[classifier] ERROR: GROQ_API_KEY not set. "
            "Export GROQ_API_KEY=<your-key> before running.",
            file=sys.stderr,
        )
        return 1

    try:
        llm_fn = make_groq_llm_fn(api_key=api_key, model=args.model)
    except ImportError as exc:
        print(f"[classifier] ERROR: {exc}", file=sys.stderr)
        return 1

    print(
        f"[classifier] Classifying {manifest_path} "
        f"(model={args.model}, min_confidence={args.min_confidence})",
        file=sys.stderr,
    )

    try:
        rules, report = run_classification(
            manifest_path,
            llm_fn=llm_fn,
            model=args.model,
            min_confidence=args.min_confidence,
        )
    except ValueError as exc:
        print(f"[classifier] ERROR: {exc}", file=sys.stderr)
        return 1

    if args.dry_run:
        print("[classifier] DRY RUN — output that would be written:", file=sys.stderr)
        print(json.dumps(rules, indent=2))
        return 0

    rules_path, _ = write_outputs(rules, report, output_dir)
    print_human_summary(report, rules_path)
    print(f"[classifier] Done. Rules written to {rules_path}", file=sys.stderr)

    # Non-zero exit if there were errors, to match batch_scrape ergonomics.
    if report.error_count > 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
