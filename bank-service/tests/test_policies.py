"""Indexing policy_chunks and GET /policies/search (Postgres + pgvector, fake embedder)."""

import json

import pytest

from app.policies import access, chunking, embeddings, store
from app.routes import policies as policies_route

pytestmark = pytest.mark.anyio

DOCS = {
    "otp": """---
level: public
---

# OTP Security

Effective date: 2026-10-01

## How long a code is valid

A one-time passcode is valid for 5 minutes after the transfer request is created.

## Wrong codes

You have 3 attempts to enter the correct passcode before the transfer is cancelled.
""",
    "savings": """---
level: public
---

# Savings Interest

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


async def keys(pool):
    async with pool.acquire() as conn:
        return (await access.create(conn, "partner", ["public"]),
                await access.create(conn, "internal", ["public", "internal"]))


def auth(key):
    return {"Authorization": f"Bearer {key}"}


class Client:
    """The test client, with a key on every request."""

    def __init__(self, client, key):
        self.client, self.key = client, key

    async def get(self, url, **kw):
        return await self.client.get(url, headers={**auth(self.key), **kw.pop("headers", {})}, **kw)


@pytest.fixture
async def indexed(bank, monkeypatch):
    client, pool, _ = bank
    async with pool.acquire() as conn:
        await store.index_chunks(conn, chunks(), embeddings.FakeEmbedder())
    monkeypatch.setattr(policies_route, "get_embedder", lambda: embeddings.FakeEmbedder())
    partner, _ = await keys(pool)
    return Client(client, partner)


async def test_search_returns_sections_with_metadata(indexed):
    r = await indexed.get("/policies/search", params={"q": "how many attempts to enter the correct passcode"})
    assert r.status_code == 200, r.text
    body = r.json()
    top = body["results"][0]
    assert (top["doc_title"], top["section"], top["effective_date"]) == ("OTP Security", "Wrong codes", "2026-10-01")
    assert "3 attempts" in top["content"] and 0 < top["score"] <= 1
    assert set(top) == {"doc_slug", "doc_title", "section", "effective_date", "content", "score"}
    assert len(body["results"]) <= 3


async def test_not_covered_is_an_empty_list(indexed, monkeypatch):
    r = await indexed.get("/policies/search", params={"q": "mortgage rates for a holiday home abroad"})
    assert r.json()["results"] == []
    monkeypatch.setenv("POLICY_VECTOR_GATE", "0.99")
    monkeypatch.setenv("POLICY_KEYWORD_GATE", "99")
    r = await indexed.get("/policies/search", params={"q": "how many attempts to enter the correct passcode"})
    assert r.json()["results"] == []


async def test_top_k_limits_results(indexed, monkeypatch):
    monkeypatch.setenv("POLICY_VECTOR_GATE", "0")
    r = await indexed.get("/policies/search", params={"q": "passcode transfer savings", "top_k": 1})
    assert len(r.json()["results"]) == 1
    r = await indexed.get("/policies/search", params={"q": "passcode transfer savings", "top_k": 5})
    assert len(r.json()["results"]) == 3  # only 3 sections exist


@pytest.mark.parametrize("params", [{"q": "hi"}, {"q": "x" * 301}, {}, {"q": "valid query", "top_k": 0},
                                    {"q": "valid query", "top_k": 6}, {"q": "valid query", "top_k": "lots"}])
async def test_search_validates_q_and_top_k(indexed, params):
    assert (await indexed.get("/policies/search", params=params)).status_code == 422


async def test_search_without_an_embedder_is_503(bank, monkeypatch):
    client, pool, _ = bank
    partner, _ = await keys(pool)
    monkeypatch.setattr(policies_route, "get_embedder", lambda: None)
    r = await client.get("/policies/search", params={"q": "valid query"}, headers=auth(partner))
    assert (r.status_code, r.json()["error"]) == (503, "POLICY_SEARCH_UNAVAILABLE")



# ── hybrid parent-child ────────────────────────────────────────────────────

LONG = {"limits": """---
level: public
---

# Transfer Limits

Effective date: 2026-10-01

## Transfers to other people

Transfers to other people are limited to $5,000 per transfer. The daily total for transfers to other people is $10,000. Transfers to other people need an OTP.

## Savings

Savings earns interest monthly.
"""}


async def index_small(pool, docs, max_tokens=12):
    out = []
    for slug, text in docs.items():
        out += chunking.parse_document(slug, text, max_tokens=max_tokens, overlap_tokens=2)
    async with pool.acquire() as conn:
        await store.index_chunks(conn, out, embeddings.FakeEmbedder())
    return out


async def test_parent_section_is_returned_once_with_its_whole_text(bank, monkeypatch):
    client, pool, _ = bank
    chunks = await index_small(pool, LONG)
    children = [c for c in chunks if c.section == "Transfers to other people"]
    assert len(children) >= 3  # several children share one parent
    monkeypatch.setattr(policies_route, "get_embedder", lambda: embeddings.FakeEmbedder())
    monkeypatch.setenv("POLICY_VECTOR_GATE", "0")
    partner, _ = await keys(pool)
    r = await client.get("/policies/search", params={"q": "transfers to other people limit per transfer daily total"},
                         headers=auth(partner))
    results = r.json()["results"]
    assert [x["section"] for x in results].count("Transfers to other people") == 1
    top = results[0]
    assert top["section"] == "Transfers to other people" and "$5,000" in top["content"] and "$10,000" in top["content"]
    assert top["content"] == children[0].section_content  # the parent, not a child
    sections = await pool.fetch("SELECT id FROM policy_sections ORDER BY id")
    assert [s["id"] for s in sections] == ["limits:savings", "limits:transfers-to-other-people"]


async def test_keyword_search_finds_exact_terms(bank):
    _, pool, _ = bank
    await index_small(pool, LONG)
    rows = await store.keyword_children(pool, "What is the OTP rule?", ["public"])
    assert rows and rows[0]["section"] == "Transfers to other people" and "OTP" in rows[0]["content"]
    assert await store.keyword_children(pool, "the and of", ["public"]) == []  # only stop words: no query


async def test_reindex_drops_parents_whose_section_is_gone(bank):
    _, pool, _ = bank
    await index_small(pool, LONG)
    await index_small(pool, {"limits": LONG["limits"].split("## Savings")[0]})
    assert [r["id"] for r in await pool.fetch("SELECT id FROM policy_sections")] == ["limits:transfers-to-other-people"]


def test_fusion_ranks_by_weighted_reciprocal_rank():
    a = {"id": "a", "parent_id": "p", "score": 0.9}
    b = {"id": "b", "parent_id": "q", "score": 0.8}
    fused = store.fuse([a, b], [{**b, "score": 1.0}], k=5, keyword_weight=0.25)
    assert [r["id"] for r in fused] == ["b", "a"]  # b: 1/7 + 0.25/6 > a: 1/6
    assert fused[0]["vector_score"] == 0.8 and fused[0]["keyword_score"] == 1.0



# ── access levels ──────────────────────────────────────────────────────────

SECRET = {"fraud": """---
level: internal
---

# Fraud Monitoring Thresholds

Effective date: 2026-11-01

## Transfer pattern alerts

A transfer to a new recipient above $2,500 is flagged. Three transfers to new recipients in one hour are flagged.

## Review times

High-risk flags are reviewed within 30 minutes.
""", "limits": LONG["limits"]}


@pytest.fixture
async def mixed(bank, monkeypatch):
    client, pool, _ = bank
    await index_small(pool, SECRET, max_tokens=400)
    monkeypatch.setattr(policies_route, "get_embedder", lambda: embeddings.FakeEmbedder())
    partner, internal = await keys(pool)
    return client, pool, partner, internal


QUESTION = "transfer to a new recipient flagged per transfer limit"


async def test_partner_never_gets_internal_chunks_from_any_query(mixed):
    _, pool, _, _ = mixed
    vec = embeddings.FakeEmbedder.vector(QUESTION)
    assert {r["doc_slug"] for r in await store.vector_children(pool, vec, "fake-embedding", ["public", "internal"])} \
        == {"fraud", "limits"}  # both match...
    assert {r["doc_slug"] for r in await store.vector_children(pool, vec, "fake-embedding", ["public"])} == {"limits"}
    assert {r["doc_slug"] for r in await store.keyword_children(pool, QUESTION, ["public"])} == {"limits"}
    assert {r["doc_slug"] for r in await store.keyword_children(pool, QUESTION, ["public", "internal"])} \
        == {"fraud", "limits"}
    internal_ids = ["fraud:transfer-pattern-alerts", "fraud:review-times"]
    assert await store.parents(pool, internal_ids, ["public"]) == {}  # even asked for by id
    assert set(await store.parents(pool, internal_ids, ["public", "internal"])) == set(internal_ids)


async def test_endpoint_levels_come_from_the_key(mixed, monkeypatch):
    client, _, partner, internal = mixed
    monkeypatch.setenv("POLICY_VECTOR_GATE", "0")
    p = (await client.get("/policies/search", params={"q": QUESTION, "top_k": 5}, headers=auth(partner))).json()
    i = (await client.get("/policies/search", params={"q": QUESTION, "top_k": 5}, headers=auth(internal))).json()
    assert {r["doc_slug"] for r in p["results"]} == {"limits"}
    assert {r["doc_slug"] for r in i["results"]} == {"fraud", "limits"}
    assert "fraud" not in json.dumps(p).lower() and "2,500" not in json.dumps(p)


async def test_hidden_matches_dont_reduce_the_partners_results(mixed, monkeypatch):
    """The internal sections rank above the public ones for this question;
    the partner still gets top_k public sections, since filtering happens
    before ranking."""
    client, _, partner, internal = mixed
    monkeypatch.setenv("POLICY_VECTOR_GATE", "0")
    i = (await client.get("/policies/search", params={"q": QUESTION, "top_k": 2}, headers=auth(internal))).json()
    assert i["results"][0]["doc_slug"] == "fraud"
    p = (await client.get("/policies/search", params={"q": QUESTION, "top_k": 2}, headers=auth(partner))).json()
    assert [r["doc_slug"] for r in p["results"]] == ["limits", "limits"]


async def test_internal_only_question_is_not_covered_for_the_partner(mixed):
    client, _, partner, internal = mixed
    q = {"q": "How fast are high-risk flags reviewed?"}
    assert (await client.get("/policies/search", params=q, headers=auth(internal))).json()["results"]
    assert (await client.get("/policies/search", params=q, headers=auth(partner))).json() == {
        "query": q["q"], "results": []}  # the same answer as any uncovered question


@pytest.mark.parametrize("headers,code", [({}, "POLICY_KEY_REQUIRED"),
                                          ({"Authorization": "Bearer pk_not-a-key"}, "POLICY_KEY_INVALID"),
                                          ({"Authorization": "Bearer mk_wrong-kind"}, "POLICY_KEY_REQUIRED")])
async def test_missing_or_invalid_key_is_401(mixed, headers, code):
    client, *_ = mixed
    r = await client.get("/policies/search", params={"q": "valid query"}, headers=headers)
    assert (r.status_code, r.json()["error"]) == (401, code)


async def test_revoked_key_is_401(mixed):
    client, pool, partner, _ = mixed
    await pool.execute("UPDATE policy_access_keys SET revoked_at = now() WHERE name = 'partner'")
    assert (await client.get("/policies/search", params={"q": "valid query"}, headers=auth(partner))).status_code == 401


@pytest.mark.parametrize("extra", [{"level": "internal"}, {"audience": "employee"}, {"levels": "public,internal"}])
async def test_level_params_are_rejected(mixed, extra):
    client, _, partner, _ = mixed
    r = await client.get("/policies/search", params={"q": "valid query", **extra}, headers=auth(partner))
    assert (r.status_code, r.json()["error"]) == (422, "UNKNOWN_PARAMETER")


async def test_reindexing_keeps_levels(mixed):
    _, pool, _, _ = mixed
    await index_small(pool, SECRET, max_tokens=400)
    rows = await pool.fetch("SELECT DISTINCT doc_slug, level FROM policy_chunks ORDER BY doc_slug")
    assert [(r["doc_slug"], r["level"]) for r in rows] == [("fraud", "internal"), ("limits", "public")]
    rows = await pool.fetch("SELECT DISTINCT doc_slug, level FROM policy_sections ORDER BY doc_slug")
    assert [(r["doc_slug"], r["level"]) for r in rows] == [("fraud", "internal"), ("limits", "public")]
    # a document moved to public is re-indexed with its new level
    await index_small(pool, {**SECRET, "fraud": SECRET["fraud"].replace("level: internal", "level: public")}, 400)
    assert await pool.fetchval("SELECT count(*) FROM policy_chunks WHERE level = 'internal'") == 0
