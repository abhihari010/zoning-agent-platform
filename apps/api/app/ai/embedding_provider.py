from __future__ import annotations

import hashlib
import math
import re

from app.ai.interfaces import EmbeddingProviderRequest, EmbeddingProviderResult


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


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    return sum(a * b for a, b in zip(left, right))
