"""GET /policies/search: Ironclad's policy documents, by meaning.

Read-only. Returns the chunks closest to the question, above a minimum
cosine similarity; nothing at all if no policy covers it."""

from __future__ import annotations

from fastapi import APIRouter, Query

from ..db import get_pool
from ..errors import BankError
from ..policies import embeddings, store

router = APIRouter(prefix="/policies", tags=["policies"])


def get_embedder():  # test seam
    return embeddings.default_embedder()


@router.get("/search")
async def search_policies(
    q: str = Query(min_length=3, max_length=300, description="The question, in plain words"),
    top_k: int = Query(default=3, ge=1, le=5),
):
    embedder = get_embedder()
    if embedder is None:
        raise BankError(503, "POLICY_SEARCH_UNAVAILABLE", "Policy search isn't configured (no embedding API key).")
    try:
        results, _ = await store.search(get_pool(), embedder, q.strip(), top_k)
    except embeddings.EmbeddingError as exc:
        raise BankError(503, "POLICY_SEARCH_UNAVAILABLE", f"Policy search is unavailable: {exc}") from exc
    return {"query": q, "results": results, "min_score": store.min_score()}
