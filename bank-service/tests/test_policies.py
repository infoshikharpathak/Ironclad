"""Indexing policy_chunks and GET /policies/search (Postgres + pgvector, fake embedder)."""

import pytest

from app.policies import chunking, embeddings, store
from app.routes import policies as policies_route

pytestmark = pytest.mark.anyio

DOCS = {
    "otp": """# OTP Security

Effective date: 2026-10-01

## How long a code is valid

A one-time passcode is valid for 5 minutes after the transfer request is created.

## Wrong codes

You have 3 attempts to enter the correct passcode before the transfer is cancelled.
""",
    "savings": """# Savings Interest

Effective date: 2026-09-01

## Interest rate

Savings earns 2.10% annual percentage yield, paid monthly.
""",
}


def chunks(docs=DOCS):
    out = []
    for slug, text in docs.items():
        out += chunking.parse_document(slug, text)
    return out


class CountingEmbedder(embeddings.FakeEmbedder):
    def __init__(self):
        self.calls = []

    async def embed(self, texts):
        self.calls.append(list(texts))
        return await super().embed(texts)


async def ids(pool):
    return sorted(r["id"] for r in await pool.fetch("SELECT id FROM policy_chunks"))


async def test_reindexing_is_idempotent_and_removes_deleted_chunks(bank):
    _, pool, _ = bank
    emb = CountingEmbedder()
    async with pool.acquire() as conn:
        first = await store.index_chunks(conn, chunks(), emb)
        again = await store.index_chunks(conn, chunks(), emb)
    assert (first.total, first.embedded, first.unchanged, first.removed) == (3, 3, 0, 0)
    assert (again.embedded, again.unchanged, again.removed) == (0, 3, 0)
    assert len(emb.calls) == 1  # the second run embedded nothing
    assert await ids(pool) == ["otp:how-long-a-code-is-valid:0", "otp:wrong-codes:0", "savings:interest-rate:0"]

    edited = {"otp": DOCS["otp"].replace("5 minutes", "10 minutes")}  # savings doc deleted, one section edited
    async with pool.acquire() as conn:
        third = await store.index_chunks(conn, chunks(edited), emb)
    assert (third.embedded, third.unchanged, third.removed) == (1, 1, 1)
    assert await ids(pool) == ["otp:how-long-a-code-is-valid:0", "otp:wrong-codes:0"]
    row = await pool.fetchrow("SELECT doc_title, section, effective_date, content FROM policy_chunks "
                              "WHERE id = 'otp:how-long-a-code-is-valid:0'")
    assert (row["doc_title"], row["section"], str(row["effective_date"])) == (
        "OTP Security", "How long a code is valid", "2026-10-01")
    assert "10 minutes" in row["content"]


@pytest.fixture
async def indexed(bank, monkeypatch):
    client, pool, _ = bank
    async with pool.acquire() as conn:
        await store.index_chunks(conn, chunks(), embeddings.FakeEmbedder())
    monkeypatch.setattr(policies_route, "get_embedder", lambda: embeddings.FakeEmbedder())
    return client


async def test_search_returns_sections_with_metadata(indexed):
    r = await indexed.get("/policies/search", params={"q": "how many attempts to enter the correct passcode"})
    assert r.status_code == 200, r.text
    body = r.json()
    top = body["results"][0]
    assert (top["doc_title"], top["section"], top["effective_date"]) == ("OTP Security", "Wrong codes", "2026-10-01")
    assert "3 attempts" in top["content"] and 0 < top["score"] <= 1
    assert set(top) == {"doc_slug", "doc_title", "section", "effective_date", "content", "score"}
    assert len(body["results"]) <= 3


async def test_nothing_above_the_minimum_score_is_an_empty_list(indexed, monkeypatch):
    r = await indexed.get("/policies/search", params={"q": "mortgage rates for a holiday home abroad"})
    assert r.json()["results"] == []
    monkeypatch.setenv("POLICY_MIN_SCORE", "0.99")
    r = await indexed.get("/policies/search", params={"q": "how many attempts to enter the correct passcode"})
    assert r.json()["results"] == [] and r.json()["min_score"] == 0.99


async def test_top_k_limits_results(indexed, monkeypatch):
    monkeypatch.setenv("POLICY_MIN_SCORE", "0")
    r = await indexed.get("/policies/search", params={"q": "passcode transfer savings", "top_k": 1})
    assert len(r.json()["results"]) == 1
    r = await indexed.get("/policies/search", params={"q": "passcode transfer savings", "top_k": 5})
    assert len(r.json()["results"]) == 3  # only 3 chunks exist


@pytest.mark.parametrize("params", [{"q": "hi"}, {"q": "x" * 301}, {}, {"q": "valid query", "top_k": 0},
                                    {"q": "valid query", "top_k": 6}, {"q": "valid query", "top_k": "lots"}])
async def test_search_validates_q_and_top_k(indexed, params):
    assert (await indexed.get("/policies/search", params=params)).status_code == 422


async def test_search_without_an_embedder_is_503(bank, monkeypatch):
    client, _, _ = bank
    monkeypatch.setattr(policies_route, "get_embedder", lambda: None)
    r = await client.get("/policies/search", params={"q": "valid query"})
    assert (r.status_code, r.json()["error"]) == (503, "POLICY_SEARCH_UNAVAILABLE")
