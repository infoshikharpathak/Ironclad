"""policy_chunks (children) and policy_sections (parents): indexing and search.

Search modes (all match against the ~60-token child chunks):

- vector:   cosine similarity (pgvector), children above MIN_SCORE.
- keyword:  Postgres full-text search (tsvector, OR of the question's terms,
            ranked with ts_rank_cd), children above KEYWORD_MIN_RANK.
- hybrid:   both, merged with reciprocal rank fusion; children.
- hybrid_parent (the default): hybrid, then grouped by parent: each matching
            ## section is returned once, with its whole text.

"Not covered": fused scores aren't similarities, so hybrid modes return
nothing unless the best child clears VECTOR_GATE on cosine similarity or
KEYWORD_GATE on full-text rank. These and the fusion settings were tuned on
the dev questions in evals/policies (see the README).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from .chunking import Chunk
from .embeddings import Embedder, cost_usd

# Tuned on the dev questions (evals/policies/compare.py; see the README).
DEFAULT_MIN_SCORE = 0.43  # vector mode
DEFAULT_KEYWORD_MIN_RANK = 0.2  # keyword mode
DEFAULT_VECTOR_GATE = 0.43  # hybrid modes: covered if the best child's cosine >= this...
DEFAULT_KEYWORD_GATE = 0.7  # ...or its full-text rank >= this
RRF_K = 5
DEFAULT_KEYWORD_WEIGHT = 0.25  # full text helps, but at full weight its common-word matches drown the vector ranking
DEFAULT_KEYWORD_FUSE_MIN = 0.0
CANDIDATES = 20  # children fetched from each ranker before fusion
MODES = ("vector", "keyword", "hybrid", "hybrid_parent")


def default_mode() -> str:
    mode = os.getenv("POLICY_SEARCH_MODE", "hybrid_parent")
    return mode if mode in MODES else "hybrid_parent"


def min_score() -> float:
    return float(os.getenv("POLICY_MIN_SCORE", DEFAULT_MIN_SCORE))


@dataclass
class Gate:
    """Return nothing unless the best child is a strong vector or keyword match."""

    vector: float = field(default_factory=lambda: float(os.getenv("POLICY_VECTOR_GATE", DEFAULT_VECTOR_GATE)))
    keyword: float = field(default_factory=lambda: float(os.getenv("POLICY_KEYWORD_GATE", DEFAULT_KEYWORD_GATE)))
    vector_min: float = field(default_factory=min_score)
    keyword_min: float = DEFAULT_KEYWORD_MIN_RANK
    # Fusion: RRF constant, the keyword ranker's weight, and the minimum
    # full-text rank for a child to enter the fusion at all.
    rrf_k: int = RRF_K
    keyword_weight: float = DEFAULT_KEYWORD_WEIGHT
    keyword_fuse_min: float = DEFAULT_KEYWORD_FUSE_MIN


def to_pgvector(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in vec) + "]"


# ── indexing ───────────────────────────────────────────────────────────────

@dataclass
class IndexReport:
    total: int
    embedded: int
    unchanged: int
    removed: int
    tokens: int
    cost_usd: float | None
    sections: int = 0


async def index_chunks(conn, chunks: list[Chunk], embedder: Embedder, *, dry_run: bool = False) -> IndexReport:
    """Embed new or changed chunks, keep unchanged ones, delete ones that no
    longer exist, and keep each chunk's parent section in policy_sections.
    One transaction: a failed run changes nothing."""
    existing = {r["id"]: r["content_hash"] for r in await conn.fetch("SELECT id, content_hash FROM policy_chunks")}
    wanted = {c.id: c for c in chunks}
    if len(wanted) != len(chunks):
        raise ValueError("duplicate chunk ids (two sections with the same name in one document?)")
    parents = {c.parent_id: c for c in chunks}
    todo = [c for c in chunks if existing.get(c.id) != c.content_hash(embedder.model)]
    stale = sorted(set(existing) - set(wanted))
    if dry_run:
        return IndexReport(len(chunks), len(todo), len(chunks) - len(todo), len(stale), 0, 0.0, len(parents))
    vectors, tokens = (await embedder.embed([c.embedding_text() for c in todo])) if todo else ([], 0)
    async with conn.transaction():
        for parent_id, c in parents.items():
            await conn.execute(
                """
                INSERT INTO policy_sections (id, doc_slug, doc_title, section, effective_date, content, content_hash)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                ON CONFLICT (id) DO UPDATE SET doc_slug = EXCLUDED.doc_slug, doc_title = EXCLUDED.doc_title,
                    section = EXCLUDED.section, effective_date = EXCLUDED.effective_date,
                    content = EXCLUDED.content, content_hash = EXCLUDED.content_hash, indexed_at = now()
                WHERE policy_sections.content_hash <> EXCLUDED.content_hash
                """,
                parent_id, c.doc_slug, c.doc_title, c.section, c.effective_date, c.section_content, c.section_hash(),
            )
        for chunk, vec in zip(todo, vectors):
            await conn.execute(
                """
                INSERT INTO policy_chunks (id, parent_id, doc_slug, doc_title, section, chunk_index, effective_date,
                                           content, content_hash, embedding_model, embedding, indexed_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11::vector, now())
                ON CONFLICT (id) DO UPDATE SET
                    parent_id = EXCLUDED.parent_id, doc_slug = EXCLUDED.doc_slug, doc_title = EXCLUDED.doc_title,
                    section = EXCLUDED.section, chunk_index = EXCLUDED.chunk_index,
                    effective_date = EXCLUDED.effective_date, content = EXCLUDED.content,
                    content_hash = EXCLUDED.content_hash, embedding_model = EXCLUDED.embedding_model,
                    embedding = EXCLUDED.embedding, indexed_at = now()
                """,
                chunk.id, chunk.parent_id, chunk.doc_slug, chunk.doc_title, chunk.section, chunk.chunk_index,
                chunk.effective_date, chunk.content, chunk.content_hash(embedder.model), embedder.model,
                to_pgvector(vec),
            )
        # Chunks indexed before parents existed get theirs.
        await conn.execute("UPDATE policy_chunks SET parent_id = split_part(id, ':', 1) || ':' || split_part(id, ':', 2) "
                           "WHERE parent_id IS NULL")
        if stale:
            await conn.execute("DELETE FROM policy_chunks WHERE id = ANY($1::text[])", stale)
        await conn.execute("DELETE FROM policy_sections WHERE NOT (id = ANY($1::text[]))", list(parents))
    return IndexReport(len(chunks), len(todo), len(chunks) - len(todo), len(stale), tokens,
                       cost_usd(embedder.model, tokens), len(parents))


# ── search ─────────────────────────────────────────────────────────────────

_CHILD_COLUMNS = "id, parent_id, doc_slug, doc_title, section, effective_date, content"


async def vector_children(pool, query_vec: list[float], model: str, limit: int = CANDIDATES) -> list[dict]:
    rows = await pool.fetch(
        f"""
        SELECT {_CHILD_COLUMNS}, 1 - (embedding <=> $1::vector) AS score
        FROM policy_chunks
        WHERE embedding_model = $2
        ORDER BY embedding <=> $1::vector
        LIMIT $3
        """,
        to_pgvector(query_vec), model, limit,
    )
    return [dict(r) | {"score": float(r["score"])} for r in rows]


async def keyword_children(pool, query: str, limit: int = CANDIDATES) -> list[dict]:
    """Full-text search: any of the question's (stemmed, stop-word-free)
    terms, ranked by ts_rank_cd. OR, not AND: a natural-language question
    rarely has every one of its words in one chunk."""
    rows = await pool.fetch(
        f"""
        WITH q AS (SELECT NULLIF(replace(plainto_tsquery('english', $1)::text, '&', '|'), '')::tsquery AS tsq)
        SELECT {_CHILD_COLUMNS}, ts_rank_cd(search_tsv, q.tsq) AS score
        FROM policy_chunks, q
        WHERE q.tsq IS NOT NULL AND search_tsv @@ q.tsq
        ORDER BY score DESC, id
        LIMIT $2
        """,
        query, limit,
    )
    return [dict(r) | {"score": float(r["score"])} for r in rows]


def fuse(vector: list[dict], keyword: list[dict], k: int = RRF_K, keyword_weight: float = 1.0) -> list[dict]:
    """Reciprocal rank fusion: score = sum of weight / (k + rank) over the
    rankers a child appears in (vector weight 1). Keeps each child's vector
    and keyword scores."""
    fused: dict[str, dict] = {}
    for name, ranked, weight in (("vector", vector, 1.0), ("keyword", keyword, keyword_weight)):
        for rank, row in enumerate(ranked, start=1):
            entry = fused.setdefault(row["id"], {**row, "vector_score": None, "keyword_score": None, "rrf": 0.0})
            entry[f"{name}_score"] = row["score"]
            entry["rrf"] += weight / (k + rank)
    return sorted(fused.values(), key=lambda r: (-r["rrf"], r["id"]))


async def parents(pool, parent_ids: list[str]) -> dict[str, dict]:
    rows = await pool.fetch(
        "SELECT id, doc_slug, doc_title, section, effective_date, content FROM policy_sections WHERE id = ANY($1::text[])",
        parent_ids,
    )
    return {r["id"]: dict(r) for r in rows}


def _result(row: dict, score: float) -> dict:
    eff = row["effective_date"]
    return {"doc_slug": row["doc_slug"], "doc_title": row["doc_title"], "section": row["section"],
            "effective_date": eff.isoformat() if eff else None, "content": row["content"], "score": round(score, 4)}


def select(vec_rows: list[dict], kw_rows: list[dict], mode: str, top_k: int, gate: Gate,
           threshold: float | None = None) -> list[tuple[dict, float]]:
    """The ranking, from the two candidate lists: (child row, score) pairs,
    or for hybrid_parent one (best child row, score) per parent section."""
    if mode not in MODES:
        raise ValueError(f"unknown search mode {mode!r}")
    if mode == "vector":
        floor = gate.vector_min if threshold is None else threshold
        return [(r, r["score"]) for r in vec_rows if r["score"] >= floor][:top_k]
    if mode == "keyword":
        return [(r, r["score"]) for r in kw_rows if r["score"] >= gate.keyword_min][:top_k]
    best_vec = max((r["score"] for r in vec_rows), default=0.0)
    best_kw = max((r["score"] for r in kw_rows), default=0.0)
    if best_vec < gate.vector and best_kw < gate.keyword:
        return []  # not covered
    fused = fuse(vec_rows, [r for r in kw_rows if r["score"] >= gate.keyword_fuse_min], gate.rrf_k, gate.keyword_weight)
    if mode == "hybrid":
        return [(r, r["rrf"]) for r in fused[:top_k]]
    out: list[tuple[dict, float]] = []
    seen: set[str] = set()
    for r in fused:  # a parent's score is its best child's
        if r["parent_id"] in seen:
            continue
        seen.add(r["parent_id"])
        out.append((r, r["rrf"]))
        if len(out) == top_k:
            break
    return out


async def candidates(pool, embedder: Embedder, query: str, mode: str) -> tuple[list[dict], list[dict], int]:
    """Vector and keyword candidates for *query* (each only if *mode* uses it)."""
    tokens = 0
    vec_rows: list[dict] = []
    if mode != "keyword":
        (vec,), tokens = await embedder.embed([query])
        vec_rows = await vector_children(pool, vec, embedder.model)
    kw_rows = await keyword_children(pool, query) if mode != "vector" else []
    return vec_rows, kw_rows, tokens


async def search(pool, embedder: Embedder, query: str, top_k: int, *, mode: str | None = None,
                 gate: Gate | None = None, threshold: float | None = None) -> tuple[list[dict], int]:
    """Results for *query* and the tokens spent embedding it. See the module
    docstring for the modes (default: POLICY_SEARCH_MODE, else hybrid_parent);
    *threshold* is the vector mode's minimum score."""
    gate = gate or Gate()
    mode = mode or default_mode()
    vec_rows, kw_rows, tokens = await candidates(pool, embedder, query, mode)
    picked = select(vec_rows, kw_rows, mode, top_k, gate, threshold)
    if mode != "hybrid_parent":
        return [_result(r, score) for r, score in picked], tokens
    sections = await parents(pool, [r["parent_id"] for r, _ in picked])
    return [_result(sections[r["parent_id"]], score) for r, score in picked if r["parent_id"] in sections], tokens
