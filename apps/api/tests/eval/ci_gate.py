"""Offline retrieval-regression gate for CI (Stage 5).

Runs the REAL pipeline (ZoningOrchestrator + hybrid_local retrieval) over every
labeled dataset in ``tests/eval/datasets/`` against a throwaway SQLite corpus
built from the committed source packs — no network, no API keys, no cost.
A chunking/ingestion/retrieval regression fails the build.

What this gates (and what it deliberately does not):

- With ``EMBEDDING_PROVIDER=none`` / ``VECTOR_PROVIDER=none``, hybrid_local
  falls back to deterministic SQL keyword retrieval. That path exercises the
  full ingestion surface (pack parsing, chunking, section_ref extraction,
  district/jurisdiction filtering, citation resolution), so the retrieval
  gates below are meaningful and stable in CI.
- ``decision_accuracy`` is NOT gated here: it measures the live analysis LLM
  (Groq in prod), and CI runs ``AI_PROVIDER=deterministic``. The full
  five-gate run against real providers remains the manual pre-promotion step
  (``python -m tests.eval.runner --jurisdiction <id>`` with prod-like env; see
  docs/handoff-pilot-city-eval-gate.md).
- ``required_citation_recall`` is gated against a PER-CITY FLOOR calibrated to
  the offline keyword-retrieval baseline (see ``CI_RECALL_FLOORS``), not the
  0.80 live-pipeline threshold. Keyword retrieval is weaker than the prod
  vector path, so the floor is a regression tripwire, not a quality claim.
  Datasets without an entry get the universal gates only, with recall
  reported but not enforced — add a floor once its offline baseline is known.

Usage (CI sets this env; the guard below refuses anything else):

    APP_ENV=local DATABASE_URL= ZONING_DB_PATH=<temp>.sqlite3 \
    AI_PROVIDER=deterministic RAG_PROVIDER=hybrid_local \
    EMBEDDING_PROVIDER=none VECTOR_PROVIDER=none \
    python -m tests.eval.ci_gate

Exit codes: 0 all gates pass; 1 a gate failed; 2 unsafe/misconfigured env.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

# Universal retrieval gates (every dataset, every run).
GATE_CITATION_VALIDITY: float = 1.0
GATE_HALLUCINATED_SECTION: float = 0.0
GATE_ABSTENTION_CORRECTNESS: float = 1.0

# Per-city required-citation-recall floors under OFFLINE keyword retrieval.
# Baselines measured 2026-07-03: montgomery-county-va 1.000, franklin-tn 0.692;
# 2026-07-04: richmond-va 0.500 (fine-grained Sec. 30-xxx.y subsection refs are
# hard for keyword retrieval; live vector recall is the quality signal).
CI_RECALL_FLOORS: dict[str, float] = {
    "montgomery-county-va": 0.80,
    # 2026-08-18 (#173): franklin-tn 0.769 -> 0.923. The pack tagged its
    # 5.1.3 use matrix ``["principal_uses"]`` with no
    # "general" AND with raw zone codes (AG, ER, R1, ...) for districts, so
    # list_source_chunks_filtered dropped it on BOTH filters -- the use filter
    # wants the inferred use or "general", the district filter wants the
    # requested category, "unknown" or "*", and raw codes are neither. Adding
    # "general" and "unknown" makes the matrix a retrieval candidate at all.
    "franklin-tn": 0.82,
    # 2026-08-17: richmond-va 0.700 (was 0.500) — same cause as hampton-va, the
    # SQL path now applies the Qdrant path's reserves, so the fine-grained
    # Sec. 30-xxx.y subsection holding the number survives the per-section cap.
    # 2026-08-18 (#173): richmond-va 0.700 -> 0.800. Each division's own
    # "Permitted principal uses." / "Permitted principal and accessory uses." /
    # "Principal uses permitted by conditional use permit." sections now carry
    # the principal_uses marker, via title-qualified clones of the 32 division
    # rules (the clones duplicate their original's districts, so no section
    # reclassifies). Narrowing the clone title to "permitted principal", which
    # drops the conditional-use-permit sections, measured the same 0.800, so the
    # broader fragment is kept -- it covers a required ref family for free.
    "richmond-va": 0.70,
    # 2026-07-14: loudoun-county-va 0.400 (Chapter 3 use-table refs; same
    # keyword-vs-table caveat as chesapeake).
    # 2026-08-18 (#173): loudoun-county-va 0.400 -> 1.000. The five 3.02.x
    # Use Table rules already targeted exactly the right
    # sections and carried their district families; they only lacked the
    # principal_uses marker, so _ensure_use_table_rows never reserved a slot.
    "loudoun-county-va": 0.90,
    # 2026-07-14: prince-william-county-va 0.700 (prose per-district
    # "Uses permitted by right" lists — keyword-friendly).
    "prince-william-county-va": 0.60,
    # 2026-07-17: albemarle-county-va 0.900 (prose per-district "By right"
    # lists; only the R-1 home-occupation ref is keyword-hard).
    "albemarle-county-va": 0.80,
    # 2026-07-17: winchester-va 0.700 (prose per-article use regulations;
    # zoning/subdivision packs share bare N-N section numbering, which
    # dilutes keyword scoring for the shortest refs).
    # 2026-08-18 (#173): winchester-va 0.700 -> 0.800, tagging each district
    # article's own "Sec. N-1. - Use regulations." section via title-qualified
    # clones of the 12 division rules. NOTE for whoever revisits this dataset:
    # two of its three required refs, "Sec. 8-1" (x4) and "Sec. 3-1" (x3),
    # resolve to the SUBDIVISION ordinance ("Exceptions.", "Administrator."),
    # not to the zoning "Use regulations." sections -- the bare N-N collision
    # noted above. Recall here can be satisfied by the wrong document; the
    # dataset, not the pack, is what needs fixing.
    "winchester-va": 0.70,
    # 2026-07-17: virginia-beach-va 1.000 (each article has ONE use chart,
    # so the per-district use vocabulary concentrates in the target section).
    "virginia-beach-va": 0.85,
    # 2026-07-17: newport-news-va 0.455 (the "Summary of uses by district" use
    # table at Sec. 45-402 is shared across 20 districts with no per-district
    # column delimiter in scraped text, so table-derived refs are keyword-hard;
    # the per-district dimensional/general sections are keyword-friendly and
    # carry most of the recall — live vector recall is the quality signal).
    # 2026-08-18 (#173): newport-news-va 0.455 -> 0.818, tagging ONLY
    # Sec. 45-402 "Summary of uses by district" -- the all-district table this
    # dataset requires in 4 of 12 scenarios. Also tagging the 19 per-district
    # "Permitted uses." sections measured 0.455 -- completely flat. Those carry
    # an exact district match (+2.0 in _score_chunk) against the summary table's
    # "unknown" (+1.2), so they took both reserved slots and crowded out the one
    # table the scenarios actually cite. Same lesson as danville-va above.
    "newport-news-va": 0.72,
    # 2026-07-17: hampton-va 0.200 (most conditional/restricted refs point at
    # Sec. 3-3 "Additional standards on uses", a single very long section
    # covering dozens of unrelated use types — its keyword vocabulary is
    # diluted the same way chesapeake's SIC use tables are; the per-district
    # dimensional sections (Sec. 4-44, 5-16, 6-3, 7-4, ...) are keyword-
    # friendly; live vector recall is the quality signal).
    # 2026-08-17: 0.400 after the SQL path started applying the same reserves as
    # the Qdrant path (see the note below the dict). Sec. 3-3's vocabulary is
    # still diluted; what changed is that _ensure_dimensional_rows now keeps the
    # number-bearing chunk of the per-district sections, which this dataset's
    # refs lean on. No pack or dataset change.
    "hampton-va": 0.30,
    # 2026-07-17: henrico-county-va 0.400 (weak-label pack: only ~35 of 442
    # sources classify to a real district after the rules fix, so most refs
    # point at Article 4 accessory-use sections whose district is "unknown" —
    # they resolve fine by keyword since each section covers one narrow use,
    # but the district-scoped base-district refs are a minority of the
    # dataset; live vector recall is the quality signal).
    "henrico-county-va": 0.35,
    # 2026-07-18: fredericksburg-va 1.000 (all 10 non-abstain scenarios cite a
    # district's own dimensional/purpose section from the "Zoning Districts"
    # article — human-authored title-level rules per district, so the refs
    # are the same short, keyword-dense sections the retriever ranks first).
    "fredericksburg-va": 0.85,
    # 2026-07-18: lynchburg-va 1.000 (all 10 non-abstain scenarios cite a
    # district's own use-standards/development-standards section from the
    # "BASE ZONING DISTRICTS" article — human-authored numeric-prefix rules
    # per district, so the refs are the same short, keyword-dense sections
    # the retriever ranks first).
    "lynchburg-va": 0.85,
    # 2026-07-18: manassas-va 1.000 (all 10 non-abstain scenarios cite a
    # district's own single all-in-one purpose/uses/dimensional section from
    # the "ZONING DISTRICTS" article — human-authored title-level rules per
    # district, same one-section-per-district shape as fredericksburg-va, so
    # the refs are the same short, keyword-dense sections the retriever
    # ranks first).
    "manassas-va": 0.85,
    # 2026-07-18: portsmouth-va 1.000 (all 10 non-abstain scenarios cite a
    # whole-category district section from the "Zoning Districts" article —
    # human-authored title_contains rules per category, one citable chunk
    # per district family, so the refs are the same short, keyword-dense
    # sections the retriever ranks first).
    "portsmouth-va": 0.85,
    # 2026-07-18: salem-va 1.000 (all 10 non-abstain scenarios cite a
    # district's own numeric-prefix section cluster from the "DISTRICT
    # REGULATIONS" article — human-authored article_contains + numeric-
    # prefix title_contains rules per district, so the refs are the same
    # short, keyword-dense sections the retriever ranks first).
    "salem-va": 0.85,
    # 2026-07-19: staunton-va 0.818 (per-district SCC chapters keyed by
    # numeric prefix like salem/lynchburg are keyword-friendly; the misses
    # are refs into the shared Article-5 special-use chapters — home
    # occupation 18.150.x, backyard hens 18.153.x — whose per-topic
    # vocabulary is diluted across sibling sections).
    "staunton-va": 0.70,
    # 2026-07-19: suffolk-va 0.600 (the UDO concentrates all districts in
    # shared giant sections — the 22-column Use Matrix at SEC. 31-406 and
    # the dimensional table at 31-407 — so table-derived refs are
    # keyword-hard; same caveat as chesapeake/newport-news, live vector
    # recall is the quality signal).
    # 2026-08-18 (#173): suffolk-va 0.600 -> 0.800. SEC. 31-406 is the
    # all-district 22-column Use Matrix and this dataset
    # requires it in 3 of 12 scenarios; a reserved slot lands it. The remaining
    # misses are Article 7 supplemental refs, unaffected by this change.
    "suffolk-va": 0.70,
    # 2026-07-19: danville-va 0.500 (Chapter 41 gives each district its own
    # ARTICLE 3.X, but the citable sections are lettered stubs — "B. -
    # Permitted Uses." — whose titles carry no district or use vocabulary,
    # so keyword scoring leans entirely on body text and misses the
    # special-use lists; live vector recall is the quality signal).
    # 2026-08-18 (#173): danville-va 0.500 -> 0.700, tagging each ARTICLE 3.X's
    # "B. - Permitted Uses." section. Tagging the sibling "C. - Uses Permitted by
    # Special Use Permit." sections TOO measured 0.500 -- flat, no gain at all.
    # _ensure_use_table_rows reserves only 2 slots and fills them from the
    # highest-ranked marked chunks, so marking twice as many sections just makes
    # them compete; danville's titles carry no district vocabulary, so the pair
    # that wins is often the wrong district's. Tag the fewest sections that ARE
    # the use listing, not every section whose title mentions permitted uses.
    "danville-va": 0.60,
    # 2026-07-19: norfolk-va 0.600 (the 2018 ordinance concentrates uses in
    # four group tables — 3.2.12/3.3.9/3.4.11/3.5.7 — shared by all
    # districts of a family, so table-derived refs are keyword-hard; same
    # caveat as suffolk/chesapeake, live vector recall is the quality
    # signal).
    # 2026-08-18 (#173): norfolk-va 0.600 -> 1.000. The four group use tables
    # (3.2.12/3.3.9/3.4.11/3.5.7) already had
    # title_contains rules carrying their district family, so tagging was a
    # one-field edit per rule.
    "norfolk-va": 0.90,
    # 2026-07-20: alexandria-va 0.800 (human-authored article_contains rules
    # over 2-level "Zoning" breadcrumbs, with numeric-prefix title_contains
    # overrides inside Article IV — each district's uses live in its own
    # keyword-dense Sec. 3-3xx/4-xxxx section, so the refs are what the
    # retriever ranks first; the misses are Article-VII supplemental refs).
    "alexandria-va": 0.70,
    # 2026-08-02: brentwood-tn 0.538 (Chapter 78 gives each district its own
    # DIVISION under ARTICLE III with a clean Municode breadcrumb, but every
    # division repeats the SAME generic section titles — "Uses permitted.",
    # "Uses prohibited.", "Limitations on home occupation uses." — with no
    # district name anywhere in the title, so keyword scoring cannot tell
    # R-1's Sec. 78-142 from R-2's 78-162 or SI-1's 78-262 and often lands on
    # the division's "Intent." section instead; same titles-carry-no-district-
    # vocabulary caveat as danville-va. The other miss is Sec. 78-14, a
    # cross-cutting Article I lot-standards section. Live vector recall is the
    # quality signal.
    "brentwood-tn": 0.45,
    # 2026-08-09: springfield-tn 0.600 (Appendix A gives each district ONE
    # all-in-one section whose title carries the district label — "A-504. R40
    # Low Density Residential Districts.", "A-603. CC Core Commercial
    # Districts." — the keyword-friendly fredericksburg/manassas shape, and
    # every residential and industrial ref lands. The misses are the six
    # commercial districts, which all list the same Chapter A-3 activity
    # names ("Food and Beverage Services", "Medical and Professional
    # Services", "General Retail Trade"), so a retail/cafe/medical-office
    # query matches A-602 through A-607 equally and the district label in the
    # title cannot break the tie while the parcel's district is unknown. The
    # remaining misses are the supporting refs A-802 and A-1306, cross-cutting
    # sections whose vocabulary is diluted across every district that points
    # at them. Live vector recall is the quality signal.
    "springfield-tn": 0.50,
    # 2026-08-12: clarksville-tn 0.286, re-authored against the corrected
    # corpus (PRs #164/#165 fixed the use-table blank-cell defect; Chapter 3
    # now reconstructs 5 real 27-column district tables instead of 0). The
    # 3.4 LAND USE TABLES section is a single ~33k-char section covering all
    # ~440 uses across all 27 districts with no per-use or per-district
    # isolation, so a "3.4" ref is keyword-hard almost everywhere — it lands
    # only for the 1/11 occurrence whose project vocabulary (Restaurant/Full
    # Service) also happens to dominate the retrieved fragment. The companion
    # PC-use standards section, 5.1 STANDARDS FOR USES PERMITTED WITH
    # CONDITIONS, is the opposite: it is prose keyed by literal use name
    # ("Bed and Breakfast:", "Veterinary Clinic: (Central Business District
    # CBD)", "Custom Manufacturing:"), so all 3/3 conditional scenarios' "5.1"
    # ref land. Live vector recall is the quality signal.
    # 2026-08-18 (#173): clarksville-tn 0.286 -> 1.000. Largest move in the
    # rollout. 3.4 LAND USE TABLES is a single ~33k-char
    # section covering ~440 uses across 27 districts, so it loses on token
    # overlap almost everywhere -- exactly the case a reserved slot is for.
    # This pack had no classification_rules.json at all; the new file holds
    # one rule and every other source still falls through to unknown/general.
    "clarksville-tn": 0.90,
    # 2026-08-12: nolensville-tn 0.769 (a form-based SmartCode: every scenario's
    # primary ref is 4.3.9 Uses, ONE section holding all three master use tables
    # — Table 4.3.9.A-1 Principal Uses plus the "D." limited-use-standards prose
    # for every PL/CU use — for all eleven Character/Civic Districts, so its
    # keyword vocabulary is broad but not diluted per scenario and "4.3.9" lands
    # for 11/12 scenarios; the lone table miss is the medical-office scenario,
    # where that vocabulary competes with dozens of other unrelated use rows.
    # The two conditional-use scenarios (group home, communications tower) also
    # require the companion Board-of-Zoning-Appeals procedural section 8.5.16,
    # a short cross-cutting reference whose keyword vocabulary (permits,
    # variances) doesn't overlap the scenario's use-specific terms — same
    # supporting-ref miss pattern as springfield's A-802/A-1306. Live vector
    # recall is the quality signal.
    # 2026-08-14: re-measured at 0.692 (one "4.3.9" hit fewer, 10/12 instead of
    # 11/12). The 0.769 above predates #169, which re-seeded a table's header row
    # into each of its chunks and so shifted this pack's keyword weighting; the
    # floor was set below both numbers and still holds. Every other one of the 26
    # datasets held its documented value exactly in that same run.
    # 2026-08-18 (#173): nolensville-tn 0.692 -> 0.846. 4.3.9 Uses holds all
    # three master use tables for all eleven Character
    # Districts. Same new-rules-file shape as clarksville-tn.
    "nolensville-tn": 0.75,
    # 2026-08-14: chesapeake-va 0.400, re-authored to co-cite each use table's
    # legend section (§ 6-2101, § 7-601, § 8-601, § 10-601 — "Key of symbols
    # used in tables"). That is a correctness fix, not a scoring one: the
    # tables' columns are headed "1F"/"2F"/"B-2"/"M1"/"A1", and ONLY the legend
    # says "1F ... includes ... R-10s" or "M1 | M-1 light industrial district",
    # so a citation to § 6-2102 alone does not let a reader confirm the parcel's
    # district maps to the column that was read. Each legend also carries the
    # numbered "Special conditions pertaining to specific uses" list that gives a
    # "C" cell its meaning, which the two CUP scenarios depend on. The legends
    # are prose and keyword-reachable (8/10 land), while the tables stay
    # keyword-hard for the pipe-dilution reason in the note below, so recall went
    # 0.100 -> 0.400 with the corpus untouched. Live vector recall is the quality
    # signal.
    #
    # 2026-08-17: chesapeake-va 0.850. The tables were never unreachable — the
    # mechanism built to reach them simply never ran here. _ensure_use_table_rows
    # reserves a retrieval slot for chunks tagged ``principal_uses``, and this
    # pack tagged nothing, so all seven "Table of permitted and conditional uses"
    # sections competed on raw token overlap and lost. Tagging them in
    # classification_rules.json (as ``["general", "principal_uses"]`` — dropping
    # "general" would exclude them from list_source_chunks_filtered's use filter
    # before scoring ever happens) puts the table in all 10 non-abstain
    # scenarios, 0.400 -> 0.850. Same run also fixed the SQL path to apply that
    # reserve at all; see the note below.
    "chesapeake-va": 0.75,
}
# chesapeake-va's use tables rank poorly on keyword score alone, which is why
# they need a reserved slot rather than a better query. The table refs held
# 0.200 while the SIC tables were flattened to "P P P P P P". After the #164
# rescrape they reconstruct correctly (§ 6-2102's three 1F columns are blank
# again), but a reconstructed table scores WORSE: a use matrix is mostly
# repeated "P"/"C"/"|" symbols, so its unique-token vocabulary per byte is a
# fraction of the prose around it, and _score_chunk's overlap term is a set
# intersection — breadth of vocabulary, not density of evidence. A table ranks
# below its own prose neighbour (a farmers-market query retrieved § 10-601
# "Description." instead of the § 10-602 table). Measured 0.000 on 2026-08-12,
# recovering to 0.100 once every table chunk carried its header row (#169).
# Nothing was lost to cause this: 0 sources removed, 0 shrank, +97 gained.
#
# 2026-08-17 correction: an earlier version of this note said keyword scoring
# "normalizes by length". It does not — _score_chunk adds
# |query ∩ chunk| / |query|, with no chunk-length term at all. The losing
# margins were tiny (measured 0.05-0.26, i.e. 1-5 query tokens, against a
# constant +4.0 from the district and use terms), which is why a reserved slot
# fixes this and query tuning would not.
#
# 2026-08-17: the SQL keyword path applied only _diversify_ranked, so
# _ensure_use_table_rows and _ensure_dimensional_rows — both pure functions of
# the ranked list, both live in the Qdrant path — never ran for it. That branch
# is not test-only: it serves any deployment without a vector store and every
# _fallback_to_sql degradation in prod, so the permitted-use table was dropped
# precisely when retrieval was already degraded. Wiring both calls in moved
# three datasets and no others (chesapeake 0.400 -> 0.850 with the tagging
# above, hampton 0.200 -> 0.400, richmond 0.500 -> 0.700; the other 23 held
# exactly). Guarded by tests/test_sql_use_table_reserve.py.
#
# Still open, and NOT fixed here: 25 of the 27 packs tag no source
# ``principal_uses`` at all, so _ensure_use_table_rows is inert for them in
# BOTH paths, prod vector retrieval included. Only franklin-tn and (as of this
# change) chesapeake-va carry the marker — and franklin-tn tags its table
# ``["principal_uses"]`` without "general", which the use filter in
# list_source_chunks_filtered drops before scoring. Tagging the rest is a
# per-city data job: each pack needs its own use-table sections identified.
#
# Why the per-district sections cannot carry recall here, unlike
# fredericksburg/manassas/salem: nothing in this pack says which district a
# district section belongs to. All 578 breadcrumbs stop at two levels ("Zoning >
# ARTICLE 7. - BUSINESS DISTRICTS"), the Municode node IDs carry no division
# segment either (ZO_ART6REDI_S6-1301DE), and the titles are bare
# "Description." / "Development standards." — so every one of these sections
# classifies to districts=['unknown'], and B-1's § 7-301, B-2's § 7-401 and
# B-5's § 7-501 are mutually indistinguishable to the retriever, which returns
# all three for any business query. Contrast brentwood-tn, same ws1 scraper,
# where Municode does expose division nodes and breadcrumbs reach depth 4
# ("... > DIVISION 2. - AR AGRICULTURAL/RESIDENTIAL ESTATE").
#
# 2026-08-17: that hypothesis is now settled — chesapeake's division headings
# are NOT being dropped by parse_content_sections, because they do not exist.
# Across the cached scrape (216 content payloads, 4,194 docs) there are 0
# DIVISION-titled docs, and across 782 TOC nodes there are 0 structural DIVISION
# nodes (the 4 apparent matches are section titles containing "subdivision").
# Chesapeake's Municode hierarchy genuinely is Zoning > Article > Section. So
# there is nothing to recover by re-fetching, and the district sections stay
# mutually indistinguishable. The use tables carry this city's recall instead.
#
# 2026-08-12 re-measurement after the #164 rescrape. hampton-va (0.200),
# henrico-county-va (0.400) and loudoun-county-va (0.400) were all rescraped
# and did NOT move, so their floors and reasoning below stand as written.
# Every one of the 19 datasets whose pack was NOT rescraped also held exactly
# steady, which is the evidence that the chunker change in #164 did not leak
# beyond the packs it was meant to fix. Note that newport-news-va's comment
# ("no per-district column delimiter in scraped text") describes the ORIGINAL
# defect and is still accurate only because that pack has not been rescraped
# yet; rescraping it should be expected to move its number the way
# chesapeake's moved.


def _require_offline_env() -> None:
    """Refuse to run unless settings are the safe offline CI configuration.

    This is the guard against the local footgun where a prod-pointing .env
    (real DATABASE_URL / Qdrant / Gemini) leaks into an eval run.
    """
    from app.settings import get_settings

    s = get_settings()
    problems: list[str] = []
    if s.ai_provider != "deterministic":
        problems.append(f"AI_PROVIDER must be 'deterministic' (got {s.ai_provider!r})")
    if s.rag_provider != "hybrid_local":
        problems.append(f"RAG_PROVIDER must be 'hybrid_local' (got {s.rag_provider!r})")
    if s.embedding_provider != "none":
        problems.append(f"EMBEDDING_PROVIDER must be 'none' (got {s.embedding_provider!r})")
    if s.vector_provider != "none":
        problems.append(f"VECTOR_PROVIDER must be 'none' (got {s.vector_provider!r})")
    if s.database_url:
        problems.append("DATABASE_URL must be unset/empty (gate runs on throwaway SQLite only)")
    if problems:
        print("[ci_gate] REFUSING to run — unsafe or misconfigured environment:")
        for p in problems:
            print(f"  - {p}")
        raise SystemExit(2)


def _bootstrap_corpus() -> None:
    """Load the committed source packs + jurisdictions into the (SQLite) store.

    Mirrors the import phase of scripts/reindex_prod.py, minus embedding.
    """
    from app.ingestion import build_source_chunks, import_source_packs
    from app.jurisdictions import jurisdiction_payloads
    from app.models import JurisdictionRecord
    from app.storage import store

    for payload in jurisdiction_payloads():
        store.upsert_jurisdiction(JurisdictionRecord.model_validate(payload))
    entries = import_source_packs()
    for entry in entries:
        store.upsert_source(entry)
    chunks = build_source_chunks(store.list_sources())
    store.replace_source_chunks(chunks)
    print(f"[ci_gate] corpus bootstrapped: {len(entries)} sources -> {len(chunks)} chunks")


def main() -> int:
    _require_offline_env()
    _bootstrap_corpus()

    from tests.eval.runner import DATASETS_DIR, load_dataset, run_eval

    dataset_paths = sorted(DATASETS_DIR.glob("*.json"))
    if not dataset_paths:
        print("[ci_gate] no datasets found — nothing to gate.")
        return 1

    all_failures: list[str] = []
    for path in dataset_paths:
        jid = path.stem
        scenarios = load_dataset(jid)
        # Scorecards go to a temp dir: the CI gate must not dirty the tree.
        with tempfile.TemporaryDirectory() as tmp:
            card = run_eval(scenarios, jid, output_dir=Path(tmp))

        failures: list[str] = []
        if card.citation_validity_rate < GATE_CITATION_VALIDITY:
            failures.append(
                f"citation_validity {card.citation_validity_rate:.3f} < {GATE_CITATION_VALIDITY}"
            )
        if card.hallucinated_section_rate > GATE_HALLUCINATED_SECTION:
            failures.append(
                f"hallucinated_section_rate {card.hallucinated_section_rate:.3f} > {GATE_HALLUCINATED_SECTION}"
            )
        if card.abstention_correctness < GATE_ABSTENTION_CORRECTNESS:
            failures.append(
                f"abstention_correctness {card.abstention_correctness:.3f} < {GATE_ABSTENTION_CORRECTNESS}"
            )
        floor = CI_RECALL_FLOORS.get(jid)
        recall_note = f"required_citation_recall={card.required_citation_recall:.3f}"
        if floor is None:
            recall_note += " (no CI floor set — reported only)"
        elif card.required_citation_recall < floor:
            failures.append(
                f"required_citation_recall {card.required_citation_recall:.3f} < CI floor {floor}"
            )

        status = "PASS" if not failures else "FAIL"
        print(
            f"[ci_gate] {jid}: {status}  n={card.scenario_count}  "
            f"citation_validity={card.citation_validity_rate:.3f}  "
            f"hallucinated={card.hallucinated_section_rate:.3f}  "
            f"abstention={card.abstention_correctness:.3f}  {recall_note}  "
            f"(decision_accuracy={card.decision_accuracy:.3f} — not gated offline)"
        )
        all_failures.extend(f"{jid}: {f}" for f in failures)

    if all_failures:
        print("[ci_gate] GATE FAILED:")
        for f in all_failures:
            print(f"  - {f}")
        return 1
    print(f"[ci_gate] all retrieval gates passed across {len(dataset_paths)} dataset(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
