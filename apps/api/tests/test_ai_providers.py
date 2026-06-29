from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from app.ai.deterministic_provider import DeterministicAnalysisProvider
from app.ai.embedding_provider import LocalHashEmbeddingProvider
from app.ai.hybrid_local_retriever import HybridLocalRetrievalProvider
from app.ai.interfaces import AnalysisProviderRequest, EmbeddingProviderRequest, RetrievalProviderRequest
from app.ai.local_model_provider import LocalModelAnalysisProvider
from app.ingestion import build_source_chunks
from app.ai.source_registry_retriever import SourceRegistryRetrievalProvider
from app.models import SourceRegistryEntry
from app.storage import SQLiteStore


def test_deterministic_provider_returns_offline_analysis() -> None:
    provider = DeterministicAnalysisProvider()

    result = provider.generate_analysis(
        AnalysisProviderRequest(
            project_description="Convert garage to bakery with employees and renovation plans.",
            district="mixed-use-core",
            citation_excerpts=[],
            missing_fields=[],
        )
    )

    assert result.decision == "conditional"
    assert "Garage-to-bakery" in result.summary


def test_source_registry_retriever_filters_by_district_and_use() -> None:
    temp_dir = Path(__file__).resolve().parent / "_tmp_provider_sources"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    try:
        source_store = SQLiteStore(temp_dir / "sources.sqlite3")
        source_store.upsert_source(
            SourceRegistryEntry(
                source_id="home-business",
                title="Home Business Rule",
                excerpt="Home occupation bakeries require review.",
                section_ref="Sec 1",
                districts=["mixed-use-core"],
                uses=["home-based-food-business"],
            )
        )
        source_store.upsert_source(
            SourceRegistryEntry(
                source_id="industrial",
                title="Industrial Rule",
                excerpt="Industrial use only.",
                section_ref="Sec 2",
                districts=["industrial-zone"],
                uses=["general"],
            )
        )

        result = SourceRegistryRetrievalProvider(source_store).retrieve(
            RetrievalProviderRequest(
                district="mixed-use-core",
                inferred_use="home-based-food-business",
                project_description="garage bakery",
            )
        )

        assert [citation.source_id for citation in result.citations] == ["home-business"]
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_source_registry_retriever_scopes_citations_by_jurisdiction() -> None:
    temp_dir = Path(__file__).resolve().parent / "_tmp_provider_jurisdiction_sources"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    try:
        source_store = SQLiteStore(temp_dir / "sources.sqlite3")
        source_store.upsert_source(
            SourceRegistryEntry(
                source_id="blacksburg-home-business",
                title="Blacksburg Home Business Rule",
                excerpt="Blacksburg home occupation bakeries require review.",
                section_ref="Sec 1",
                jurisdiction_id="blacksburg-va",
                districts=["unknown"],
                uses=["home-based-food-business"],
            )
        )
        source_store.upsert_source(
            SourceRegistryEntry(
                source_id="montgomery-home-occupation",
                title="Montgomery County Home Occupation Rule",
                excerpt="Montgomery County home occupations require zoning, health, and inspections review.",
                section_ref="Home Occupations",
                jurisdiction_id="montgomery-county-va",
                districts=["unknown"],
                uses=["home-based-food-business"],
            )
        )

        result = SourceRegistryRetrievalProvider(source_store).retrieve(
            RetrievalProviderRequest(
                district="unknown",
                inferred_use="home-based-food-business",
                project_description="garage bakery",
                jurisdiction_id="montgomery-county-va",
            )
        )

        assert [citation.source_id for citation in result.citations] == ["montgomery-home-occupation"]
        assert all("Blacksburg" not in citation.title for citation in result.citations)
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_local_embedding_provider_is_deterministic() -> None:
    provider = LocalHashEmbeddingProvider(dimensions=8)

    first = provider.embed(EmbeddingProviderRequest(texts=["home bakery parking"])).embeddings[0]
    second = provider.embed(EmbeddingProviderRequest(texts=["home bakery parking"])).embeddings[0]

    assert first == second
    assert len(first) == 8


def test_hybrid_local_retriever_uses_indexed_chunks() -> None:
    temp_dir = Path(__file__).resolve().parent / "_tmp_hybrid_sources"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    try:
        source_store = SQLiteStore(temp_dir / "sources.sqlite3")
        source_store.upsert_source(
            SourceRegistryEntry(
                source_id="bakery-rule",
                title="Bakery Rule",
                excerpt="Home occupation bakeries require parking and fire review.",
                section_ref="Sec 10.2",
                districts=["mixed-use-core"],
                uses=["home-based-food-business"],
            )
        )
        source_store.replace_source_chunks(build_source_chunks(source_store.list_sources()))

        result = HybridLocalRetrievalProvider(
            source_store,
            embedding_provider=LocalHashEmbeddingProvider(),
        ).retrieve(
            RetrievalProviderRequest(
                district="mixed-use-core",
                inferred_use="home-based-food-business",
                project_description="garage bakery parking",
            )
        )

        assert result.citations
        assert result.citations[0].source_id == "bakery-rule"
        assert "parking" in result.citations[0].excerpt
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_hybrid_local_retriever_falls_back_to_sql_when_qdrant_has_no_hits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VECTOR_PROVIDER", "qdrant")
    monkeypatch.setenv("QDRANT_URL", "http://localhost:6333")
    temp_dir = Path(__file__).resolve().parent / "_tmp_hybrid_empty_qdrant"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    try:
        source_store = SQLiteStore(temp_dir / "sources.sqlite3")
        source_store.upsert_source(
            SourceRegistryEntry(
                source_id="coffee-rule",
                title="Coffee Rule",
                excerpt="Coffee shops require parking review.",
                section_ref="Sec 10.2",
                jurisdiction_id="blacksburg-va",
                districts=["mixed-use-core"],
                uses=["food_service"],
            )
        )
        source_store.replace_source_chunks(build_source_chunks(source_store.list_sources()))
        monkeypatch.setattr("app.rag.vector_store.QdrantVectorStore.query", lambda *args, **kwargs: [])

        result = HybridLocalRetrievalProvider(
            source_store,
            embedding_provider=LocalHashEmbeddingProvider(),
        ).retrieve(
            RetrievalProviderRequest(
                district="mixed-use-core",
                inferred_use="food_service",
                project_description="coffee shop",
                jurisdiction_id="blacksburg-va",
            )
        )

        assert [citation.source_id for citation in result.citations] == ["coffee-rule"]
        assert result.chunks
        assert result.diagnostics is not None
        assert result.diagnostics.vector_hit_count == 0
        assert result.diagnostics.fallback_used is True
        assert result.diagnostics.fallback_reason == "Qdrant returned no matching points"
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_local_model_provider_uses_openai_compatible_chat_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("AI_PROVIDER", "local")
    monkeypatch.setenv("LOCAL_MODEL_BASE_URL", "http://localhost:1234/v1")
    monkeypatch.setenv("LOCAL_MODEL_NAME", "local-test-model")

    class FakeResponse:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"decision":"conditional","summary":"Evidence indicates review is needed.",'
                                '"required_permits":["Zoning Permit"],"follow_up_questions":[],"warnings":[]}'
                            )
                        }
                    }
                ]
            }

    captured: dict = {}

    def fake_post(url: str, headers: dict, json: dict, timeout: float):
        captured["url"] = url
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("app.ai.local_model_provider.httpx.post", fake_post)

    result = LocalModelAnalysisProvider().generate_analysis(
        AnalysisProviderRequest(
            project_description="Open a small coffee shop.",
            district="mixed-use-core",
            citation_excerpts=["Food service may require review."],
            missing_fields=[],
        )
    )

    assert captured["url"] == "http://localhost:1234/v1/chat/completions"
    assert captured["json"]["model"] == "local-test-model"
    assert result.decision == "conditional"
    assert result.required_permits == ["Zoning Permit"]


def _blacksburg_chunk(districts: list[str]):
    source = SourceRegistryEntry(
        source_id="sec-3061",
        title="Sec. 3061 - Permitted uses",
        excerpt="Restaurants and cafes are permitted uses subject to site standards.",
        section_ref="Sec. 3061",
        jurisdiction_id="blacksburg-va",
        districts=districts,
        uses=["general"],
        source_type="zoning_ordinance",
    )
    return build_source_chunks([source])[0]


def test_hybrid_local_sql_path_surfaces_unknown_district_ordinance() -> None:
    # End-to-end fallback (SQL) path. An unclassified ordinance chunk
    # (districts=["unknown"]) must be retrievable for a concrete-district query,
    # while a chunk tagged with a *different* concrete district stays excluded.
    # Guards both list_source_chunks_filtered (candidate gate) and _score_chunk
    # (re-ranker) against the district-asymmetry bug.
    temp_dir = Path(__file__).resolve().parent / "_tmp_hybrid_unknown_district"
    if temp_dir.exists():
        shutil.rmtree(temp_dir)
    temp_dir.mkdir(parents=True)

    try:
        source_store = SQLiteStore(temp_dir / "sources.sqlite3")
        source_store.upsert_source(
            SourceRegistryEntry(
                source_id="sec-3061-permitted-uses",
                title="Sec. 3061 - Permitted uses",
                excerpt="Restaurants and cafes are permitted uses in the district subject to site standards.",
                section_ref="Sec. 3061",
                jurisdiction_id="blacksburg-va",
                districts=["unknown"],
                uses=["general"],
            )
        )
        source_store.upsert_source(
            SourceRegistryEntry(
                source_id="residential-only-rule",
                title="Residential-only standard",
                excerpt="This standard applies only in the residential low density district.",
                section_ref="Sec. 9000",
                jurisdiction_id="blacksburg-va",
                districts=["residential-low-density"],
                uses=["general"],
            )
        )
        source_store.replace_source_chunks(build_source_chunks(source_store.list_sources()))

        result = HybridLocalRetrievalProvider(
            source_store,
            embedding_provider=LocalHashEmbeddingProvider(),
        ).retrieve(
            RetrievalProviderRequest(
                district="mixed-use-core",
                inferred_use="food-service",
                project_description="Open a small coffee shop in an existing storefront",
                jurisdiction_id="blacksburg-va",
            )
        )

        returned = {citation.source_id for citation in result.citations}
        assert "sec-3061-permitted-uses" in returned
        assert "residential-only-rule" not in returned
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def test_score_chunk_exact_district_beats_unknown_wildcard() -> None:
    # Re-ranker symmetry: an unclassified (districts=["unknown"]) chunk must earn
    # the same district credit as a chunk tagged with the queried district,
    # mirroring how uses=["general"] is treated as a wildcard. Otherwise unlocking
    # the unknown-tagged ordinance corpus in the filter is moot — the home-occupation
    # seeds (tagged with the district) keep a +2.0 head start and still win top-5.
    from app.ai.hybrid_local_retriever import _score_chunk, _tokens

    request = RetrievalProviderRequest(
        district="mixed-use-core",
        inferred_use="food-service",
        project_description="Open a small coffee shop in an existing storefront",
        jurisdiction_id="blacksburg-va",
    )
    query_tokens = _tokens(request.query)

    unknown_score = _score_chunk(_blacksburg_chunk(["unknown"]), request, query_tokens)
    tagged_score = _score_chunk(_blacksburg_chunk(["mixed-use-core"]), request, query_tokens)

    assert unknown_score > 0
    assert tagged_score > unknown_score


def test_score_chunk_additive_tag_outranks_wrong_district_wildcard() -> None:
    # Layer-2 precision: after additive tagging a chunk gets both "unknown" AND a
    # real district. For a concrete-district query, the chunk whose canonical district
    # matches earns an exact-match bonus (+2.0) while the chunk whose canonical
    # district doesn't match only earns the wildcard credit (+1.2), and both stay > 0
    # (recall preserved).
    from app.ai.hybrid_local_retriever import _score_chunk, _tokens

    request = RetrievalProviderRequest(
        district="residential-low-density",
        inferred_use="general",
        project_description="Build a residential addition",
        jurisdiction_id="blacksburg-va",
    )
    query_tokens = _tokens(request.query)

    residential_chunk = _blacksburg_chunk(["unknown", "residential-low-density"])
    commercial_chunk = _blacksburg_chunk(["unknown", "commercial-employment"])

    res_score = _score_chunk(residential_chunk, request, query_tokens)
    com_score = _score_chunk(commercial_chunk, request, query_tokens)

    assert res_score > 0
    assert com_score > 0
    assert res_score > com_score


def test_openai_compatible_provider_posts_and_coerces_unlisted_use(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.ai.openai_compatible import OpenAICompatibleAnalysisProvider

    class FakeResponse:
        status_code = 200

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict:
            # Model commits to 'restricted' but flags the use as unlisted; the
            # provider must structurally coerce the decision to 'unknown'.
            return {
                "choices": [
                    {
                        "message": {
                            "content": (
                                '{"decision":"restricted","summary":"Industrial reading.",'
                                '"required_permits":[],"follow_up_questions":[],"warnings":[],'
                                '"unlisted_use_determination":true}'
                            )
                        }
                    }
                ]
            }

    captured: dict = {}

    def fake_post(url: str, headers: dict, json: dict, timeout: float):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        return FakeResponse()

    monkeypatch.setattr("app.ai.openai_provider.httpx.post", fake_post)

    provider = OpenAICompatibleAnalysisProvider(
        name="cerebras",
        base_url="https://api.cerebras.ai/v1",
        api_key="test-key",
        model="llama-3.3-70b",
        timeout=20.0,
    )
    result = provider.generate_analysis(
        AnalysisProviderRequest(
            project_description="Open a standalone craft brewery with a taproom.",
            district="unknown",
            citation_excerpts=["Subsection 5.2.7.I.3 industrial classification."],
            missing_fields=[],
        )
    )

    assert captured["url"] == "https://api.cerebras.ai/v1/chat/completions"
    assert captured["json"]["model"] == "llama-3.3-70b"
    assert captured["headers"]["Authorization"] == "Bearer test-key"
    assert result.decision == "unknown"
    assert any("similar-use determination" in w for w in result.warnings)


def test_openai_compatible_provider_requires_api_key() -> None:
    from app.ai.openai_compatible import OpenAICompatibleAnalysisProvider

    provider = OpenAICompatibleAnalysisProvider(
        name="openrouter",
        base_url="https://openrouter.ai/api/v1",
        api_key="",
        model="x",
        timeout=20.0,
    )
    with pytest.raises(RuntimeError):
        provider.generate_analysis(
            AnalysisProviderRequest(
                project_description="x", district="unknown", citation_excerpts=[], missing_fields=[]
            )
        )


class _BoomProvider:
    name = "boom"

    def __init__(self) -> None:
        self.calls = 0

    def generate_analysis(self, request):  # noqa: ANN001
        self.calls += 1
        raise RuntimeError("rate limited")


class _OkProvider:
    def __init__(self, name: str = "ok") -> None:
        self.name = name
        self.calls = 0

    def generate_analysis(self, request):  # noqa: ANN001
        from app.ai.interfaces import AnalysisProviderResult

        self.calls += 1
        return AnalysisProviderResult(decision="likely_allowed", summary=f"{self.name} ok")


def test_failover_advances_to_next_provider_on_failure() -> None:
    from app.ai.failover_provider import FailoverAnalysisProvider

    boom = _BoomProvider()
    ok = _OkProvider("cerebras")
    request = AnalysisProviderRequest(
        project_description="x", district="unknown", citation_excerpts=[], missing_fields=[]
    )

    result = FailoverAnalysisProvider([boom, ok]).generate_analysis(request)

    assert result.summary == "cerebras ok"
    assert boom.calls == 1
    assert ok.calls == 1


def test_failover_short_circuits_on_primary_success() -> None:
    from app.ai.failover_provider import FailoverAnalysisProvider

    primary = _OkProvider("groq")
    secondary = _OkProvider("cerebras")
    request = AnalysisProviderRequest(
        project_description="x", district="unknown", citation_excerpts=[], missing_fields=[]
    )

    FailoverAnalysisProvider([primary, secondary]).generate_analysis(request)

    assert primary.calls == 1
    assert secondary.calls == 0  # never reached


def test_failover_reraises_when_all_providers_fail() -> None:
    from app.ai.failover_provider import FailoverAnalysisProvider

    request = AnalysisProviderRequest(
        project_description="x", district="unknown", citation_excerpts=[], missing_fields=[]
    )
    with pytest.raises(RuntimeError):
        FailoverAnalysisProvider([_BoomProvider(), _BoomProvider()]).generate_analysis(request)


def test_registry_wraps_failover_only_when_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.ai.failover_provider import FailoverAnalysisProvider
    from app.ai.groq_provider import GroqAnalysisProvider
    from app.ai.registry import get_analysis_provider
    from app.settings import get_settings

    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("AI_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "g")
    monkeypatch.setenv("CEREBRAS_API_KEY", "c")
    monkeypatch.setenv("OPENROUTER_API_KEY", "")  # keyless fallback must be skipped

    # No fallbacks configured -> single pinned provider (this is the eval path).
    monkeypatch.setenv("AI_PROVIDER_FALLBACKS", "")
    pinned = get_analysis_provider(get_settings())
    assert isinstance(pinned, GroqAnalysisProvider)

    # Fallbacks configured -> failover chain, skipping the keyless openrouter.
    monkeypatch.setenv("AI_PROVIDER_FALLBACKS", "cerebras,openrouter")
    chained = get_analysis_provider(get_settings())
    assert isinstance(chained, FailoverAnalysisProvider)
    assert "cerebras" in chained.name
    assert "openrouter" not in chained.name


def test_source_index_version_changes_when_only_tags_change(tmp_path: Path) -> None:
    from app.ai.hybrid_local_retriever import _source_index_version

    source_store = SQLiteStore(tmp_path / "sources.sqlite3")
    base = SourceRegistryEntry(
        source_id="stable-rule",
        title="Stable Rule",
        excerpt="Coffee shops require zoning review with sufficient text for chunking.",
        full_text="Coffee shops require zoning review with sufficient text for chunking.",
        section_ref="Sec. 1",
        jurisdiction_id="blacksburg-va",
        districts=["unknown"],
        uses=["general"],
    )
    source_store.replace_source_chunks(build_source_chunks([base]))
    first = _source_index_version(source_store, "")

    tagged = base.model_copy(update={"districts": ["unknown", "commercial-employment"]})
    source_store.replace_source_chunks(build_source_chunks([tagged]))
    second = _source_index_version(source_store, "")

    assert first != second


def _one_chunk() -> list:
    entry = SourceRegistryEntry(
        source_id="memo-rule",
        title="Memo Rule",
        excerpt="Coffee shops require zoning review with sufficient text for chunking.",
        full_text="Coffee shops require zoning review with sufficient text for chunking.",
        section_ref="Sec. 1",
        jurisdiction_id="blacksburg-va",
        districts=["unknown"],
        uses=["general"],
    )
    return build_source_chunks([entry])


def test_source_index_version_memoized_for_global_store(monkeypatch) -> None:
    from app.ai import hybrid_local_retriever as hlr

    hlr.reset_source_index_version_memo()
    chunks = _one_chunk()
    scans = {"n": 0}

    def _counting_list() -> list:
        scans["n"] += 1
        return chunks

    monkeypatch.setattr(hlr.store, "get_source_count", lambda: 1)
    monkeypatch.setattr(hlr.store, "get_source_chunk_count", lambda: len(chunks))
    monkeypatch.setattr(hlr.store, "list_source_chunks", _counting_list)

    first = hlr._source_index_version(hlr.store, "")
    second = hlr._source_index_version(hlr.store, "")
    assert first == second
    assert scans["n"] == 1  # second call served from the memo, no corpus scan

    # Changing the cheap count signature busts the memo and forces a re-scan.
    monkeypatch.setattr(hlr.store, "get_source_chunk_count", lambda: len(chunks) + 1)
    hlr._source_index_version(hlr.store, "")
    assert scans["n"] == 2
    hlr.reset_source_index_version_memo()


def test_ensure_source_index_ready_cheap_when_startup_reindex_disabled(monkeypatch) -> None:
    from types import SimpleNamespace

    from app.ai import source_registry_retriever as srr

    srr.reset_source_index_readiness_memo()
    monkeypatch.setattr(srr, "ensure_seed_sources", lambda *a, **k: None)
    monkeypatch.setattr(srr, "get_settings", lambda: SimpleNamespace(startup_reindex_enabled=False))
    monkeypatch.setattr(srr.store, "get_source_count", lambda: 5)
    monkeypatch.setattr(srr.store, "get_source_chunk_count", lambda: 42)

    def _boom(*a, **k):
        raise AssertionError("must not load the corpus when startup reindex is disabled")

    monkeypatch.setattr(srr.store, "list_sources", _boom)
    monkeypatch.setattr(srr.store, "list_source_chunks", _boom)

    readiness = srr.ensure_source_index_ready(srr.store)
    assert readiness.index_ready is True
    assert readiness.source_count == 5
    assert readiness.chunk_count == 42


def test_ensure_source_index_ready_memoized_for_global_store(monkeypatch) -> None:
    from types import SimpleNamespace

    from app.ai import source_registry_retriever as srr

    srr.reset_source_index_readiness_memo()
    monkeypatch.setattr(srr, "ensure_seed_sources", lambda *a, **k: None)
    # Force the full reconciliation path (not the externally-managed cheap path).
    monkeypatch.setattr(
        srr,
        "get_settings",
        lambda: SimpleNamespace(startup_reindex_enabled=True, auto_reindex_on_empty=False),
    )

    entry = SourceRegistryEntry(
        source_id="memo-rule",
        title="Memo Rule",
        excerpt="Coffee shops require zoning review with sufficient text for chunking.",
        full_text="Coffee shops require zoning review with sufficient text for chunking.",
        section_ref="Sec. 1",
        jurisdiction_id="blacksburg-va",
        districts=["unknown"],
        uses=["general"],
    )
    chunks = build_source_chunks([entry])
    scans = {"n": 0}

    def _counting_chunks() -> list:
        scans["n"] += 1
        return chunks

    monkeypatch.setattr(srr.store, "get_source_count", lambda: 1)
    monkeypatch.setattr(srr.store, "get_source_chunk_count", lambda: len(chunks))
    monkeypatch.setattr(srr.store, "list_sources", lambda: [entry])
    monkeypatch.setattr(srr.store, "list_source_chunks", _counting_chunks)

    first = srr.ensure_source_index_ready(srr.store)
    second = srr.ensure_source_index_ready(srr.store)
    assert first is second  # memo returns the same readiness object
    assert scans["n"] == 1  # second call did not reload/rebuild the corpus
    srr.reset_source_index_readiness_memo()


