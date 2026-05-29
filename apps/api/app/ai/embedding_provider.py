from __future__ import annotations

import hashlib
import math
import re
import time

from app.ai.interfaces import EmbeddingProviderRequest, EmbeddingProviderResult

# Gemini exposes an OpenAI-compatible embeddings endpoint. Groq has no embeddings API.
GEMINI_EMBEDDINGS_URL = "https://generativelanguage.googleapis.com/v1beta/openai/embeddings"


TOKEN_PATTERN = re.compile(r"[a-z0-9]+")


class DisabledEmbeddingProvider:
    name = "none"

    def embed(self, request: EmbeddingProviderRequest) -> EmbeddingProviderResult:
        return EmbeddingProviderResult(embeddings=[[] for _ in request.texts])


class LocalHashEmbeddingProvider:
    name = "local"

    def __init__(self, dimensions: int = 64) -> None:
        self.dimensions = dimensions

    def embed(self, request: EmbeddingProviderRequest) -> EmbeddingProviderResult:
        return EmbeddingProviderResult(
            embeddings=[self._embed_text(text) for text in request.texts]
        )

    def _embed_text(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        for token in TOKEN_PATTERN.findall(text.lower()):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:2], "big") % self.dimensions
            weight = 1.0 if digest[2] % 2 == 0 else -1.0
            vector[index] += weight

        magnitude = math.sqrt(sum(value * value for value in vector))
        if magnitude == 0:
            return vector
        return [value / magnitude for value in vector]


class GeminiEmbeddingProvider:
    name = "gemini"

    def embed(self, request: EmbeddingProviderRequest) -> EmbeddingProviderResult:
        from app.ai.openai_provider import _post_with_retry
        from app.settings import get_settings

        if not request.texts:
            return EmbeddingProviderResult(embeddings=[])

        settings = get_settings()
        batch_size = settings.gemini_embedding_batch_size or len(request.texts)
        headers = {
            "Authorization": f"Bearer {settings.gemini_api_key}",
            "Content-Type": "application/json",
        }

        embeddings: list[list[float]] = []
        total = len(request.texts)
        for start in range(0, total, batch_size):
            batch = request.texts[start : start + batch_size]
            body: dict = {
                "model": settings.gemini_embedding_model,
                "input": batch,
                "encoding_format": "float",
            }
            # gemini-embedding-001 uses Matryoshka Representation Learning; request a
            # smaller, storage-friendly vector when configured (default 3072 if 0/unset).
            if settings.gemini_embedding_dimensions:
                body["dimensions"] = settings.gemini_embedding_dimensions

            payload = _post_with_retry(
                url=GEMINI_EMBEDDINGS_URL,
                headers=headers,
                body=body,
                timeout=settings.gemini_timeout_seconds,
                # Free-tier Gemini is RPM/TPM limited; retry 429s instead of failing the
                # whole reindex on the first rate-limit response.
                extra_retry_statuses={429},
                max_attempts=5,
            )
            data = payload.get("data", [])
            # Gemini returns un-normalized vectors when dimensions are truncated below
            # 3072. Normalize so dot-product cosine (hybrid retriever) stays valid.
            embeddings.extend(
                _normalize(item.get("embedding", []))
                for item in sorted(data, key=lambda item: item.get("index", 0))
            )
            # Space out batches to stay under the free-tier requests-per-minute limit.
            if start + batch_size < total and settings.gemini_embedding_request_interval_seconds > 0:
                time.sleep(settings.gemini_embedding_request_interval_seconds)

        return EmbeddingProviderResult(embeddings=embeddings)


def _normalize(vector: list[float]) -> list[float]:
    magnitude = math.sqrt(sum(value * value for value in vector))
    if magnitude == 0:
        return vector
    return [value / magnitude for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))
