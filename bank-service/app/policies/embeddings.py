"""Embedders: OpenAI's text-embedding-3-small over HTTP, and a deterministic
fake for tests (no API key)."""

from __future__ import annotations

import hashlib
import math
import os
import re
from typing import Protocol

import httpx

DIMENSIONS = 1536
DEFAULT_MODEL = "text-embedding-3-small"
# USD per 1M input tokens, from https://developers.openai.com/api/docs/pricing
# (Specialized models, Standard), checked 2026-11-22. The same figure is in
# Agent Forge's shared table (agent_forge.pricing); the bank service doesn't
# depend on Agent Forge, so it's repeated here.
PRICE_PER_1M = {"text-embedding-3-small": 0.02, "text-embedding-3-large": 0.13}


class Embedder(Protocol):
    model: str

    async def embed(self, texts: list[str]) -> tuple[list[list[float]], int]:
        """(vectors, tokens used)"""


class EmbeddingError(Exception):
    pass


class OpenAIEmbedder:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, *, transport: httpx.AsyncBaseTransport | None = None):
        self.model = model
        self._key = api_key
        self._transport = transport

    async def embed(self, texts: list[str]) -> tuple[list[list[float]], int]:
        vectors: list[list[float]] = []
        tokens = 0
        async with httpx.AsyncClient(timeout=30, transport=self._transport) as client:
            for start in range(0, len(texts), 96):
                batch = texts[start:start + 96]
                resp = await client.post(
                    "https://api.openai.com/v1/embeddings",
                    headers={"Authorization": f"Bearer {self._key}"},
                    json={"model": self.model, "input": batch},
                )
                if resp.status_code >= 400:
                    raise EmbeddingError(f"OpenAI embeddings returned {resp.status_code}: {resp.text[:200]}")
                body = resp.json()
                vectors += [d["embedding"] for d in sorted(body["data"], key=lambda d: d["index"])]
                tokens += body.get("usage", {}).get("total_tokens", 0)
        return vectors, tokens


class FakeEmbedder:
    """Bag of words hashed into DIMENSIONS buckets, L2-normalised: texts that
    share words are close. Deterministic, free, offline."""

    model = "fake-embedding"

    async def embed(self, texts: list[str]) -> tuple[list[list[float]], int]:
        return [self.vector(t) for t in texts], sum(len(t.split()) for t in texts)

    @staticmethod
    def vector(text: str) -> list[float]:
        v = [0.0] * DIMENSIONS
        for word in re.findall(r"[a-z0-9$]+", text.lower()):
            v[int(hashlib.md5(word.encode()).hexdigest(), 16) % DIMENSIONS] += 1.0
        norm = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / norm for x in v]


def cost_usd(model: str, tokens: int) -> float | None:
    price = PRICE_PER_1M.get(model)
    return None if price is None else round(tokens * price / 1_000_000, 6)


def default_embedder() -> Embedder | None:
    """The configured embedder, or None if there's no OPENAI_API_KEY."""
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    return OpenAIEmbedder(key, os.getenv("POLICY_EMBEDDING_MODEL", DEFAULT_MODEL))
