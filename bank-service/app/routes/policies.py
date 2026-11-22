"""GET /policies/search: Ironclad's policy documents.

Read-only. Hybrid search (vector + full-text over small chunks, fused),
returning each matching ## section once; nothing at all if no policy
covers the question (see app/policies/store.py).

Needs a policy-access key ('Authorization: Bearer pk_...'). The key alone
decides which levels of documents (public, internal) are searched; the
request can't ask for a level, and a caller is never told that documents it
can't read exist.
"""

from __future__ import annotations

from fastapi import APIRouter, Header, Query, Request

from ..db import get_pool
from ..errors import BankError
from ..policies import access, embeddings, store

router = APIRouter(prefix="/policies", tags=["policies"])

ALLOWED_PARAMS = {"q", "top_k"}


def get_embedder():  # test seam
    return embeddings.default_embedder()


@router.get("/search")
async def search_policies(
    request: Request,
    q: str = Query(min_length=3, max_length=300, description="The question, in plain words"),
    top_k: int = Query(default=3, ge=1, le=5),
    authorization: str | None = Header(default=None),
):
    key = access.bearer_key(authorization)
    if key is None:
        raise BankError(401, "POLICY_KEY_REQUIRED", "Send a policy-access key as 'Authorization: Bearer pk_...'.")
    levels = await access.levels_for(get_pool(), key)
    if levels is None:
        raise BankError(401, "POLICY_KEY_INVALID", "Unknown or revoked policy-access key.")
    extra = sorted(set(request.query_params) - ALLOWED_PARAMS)
    if extra:  # e.g. level=internal: access comes from the key, never from the request
        raise BankError(422, "UNKNOWN_PARAMETER", f"Unknown parameter(s): {', '.join(extra)}.", {"params": extra})
    embedder = get_embedder()
    if embedder is None:
        raise BankError(503, "POLICY_SEARCH_UNAVAILABLE", "Policy search isn't configured (no embedding API key).")
    try:
        results, _ = await store.search(get_pool(), embedder, q.strip(), top_k, levels=levels)
    except embeddings.EmbeddingError as exc:
        raise BankError(503, "POLICY_SEARCH_UNAVAILABLE", f"Policy search is unavailable: {exc}") from exc
    return {"query": q, "results": results}
