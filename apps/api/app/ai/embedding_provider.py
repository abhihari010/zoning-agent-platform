from __future__ import annotations

import hashlib
import math
import re

from app.ai.interfaces import EmbeddingProviderRequest, EmbeddingProviderResult

GROQ_EMBEDDINGS_URL = "https://api.groq.com/openai/v1/embeddings"


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


class GroqEmbeddingProvider:
    name = "groq"

    def embed(self, request: EmbeddingProviderRequest) -> EmbeddingProviderResult:
        from app.ai.openai_provider import _post_with_retry
        from app.settings import get_settings

        if not request.texts:
            return EmbeddingProviderResult(embeddings=[])

        settings = get_settings()
        payload = _post_with_retry(
            url=GROQ_EMBEDDINGS_URL,
            headers={
                "Authorization": f"Bearer {settings.groq_api_key}",
                "Content-Type": "application/json",
            },
            body={
                "model": settings.groq_embedding_model,
                "input": request.texts,
                "encoding_format": "float",
            },
            timeout=settings.groq_timeout_seconds,
        )
        data = payload.get("data", [])
        embeddings = [
            item.get("embedding", [])
            for item in sorted(data, key=lambda item: item.get("index", 0))
        ]
        return EmbeddingProviderResult(embeddings=embeddings)


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))
