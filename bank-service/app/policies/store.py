"""policy_chunks: indexing and search (pgvector, cosine similarity)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from .chunking import Chunk
from .embeddings import Embedder, cost_usd

# Results below this cosine similarity are dropped, so a question the
# policies don't answer gets an empty list instead of weak matches. Chosen
# with evals/policies (see the README): at 0.43 every answerable question
# still returns results and every unanswerable one returns none, but only
# just (the weakest right answer scored 0.434, the strongest unanswerable
# question 0.428). Override with POLICY_MIN_SCORE.
DEFAULT_MIN_SCORE = 0.43


def min_score() -> float:
    return float(os.getenv("POLICY_MIN_SCORE", DEFAULT_MIN_SCORE))


def to_pgvector(vec: list[float]) -> str:
    return "[" + ",".join(f"{x:.7g}" for x in vec) + "]"


@dataclass
class IndexReport:
    total: int
    embedded: int
    unchanged: int
    removed: int
    tokens: int
    cost_usd: float | None


async def index_chunks(conn, chunks: list[Chunk], embedder: Embedder, *, dry_run: bool = False) -> IndexReport:
    """Embed new or changed chunks, keep unchanged ones, delete ones that no
    longer exist. One transaction: a failed run changes nothing."""
    existing = {r["id"]: r["content_hash"] for r in await conn.fetch("SELECT id, content_hash FROM policy_chunks")}
    wanted = {c.id: c for c in chunks}
    if len(wanted) != len(chunks):
        raise ValueError("duplicate chunk ids (two sections with the same name in one document?)")
    todo = [c for c in chunks if existing.get(c.id) != c.content_hash(embedder.model)]
    stale = sorted(set(existing) - set(wanted))
    if dry_run:
        return IndexReport(len(chunks), len(todo), len(chunks) - len(todo), len(stale), 0, 0.0)
    vectors, tokens = (await embedder.embed([c.embedding_text() for c in todo])) if todo else ([], 0)
    async with conn.transaction():
        for chunk, vec in zip(todo, vectors):
            await conn.execute(
                """
                INSERT INTO policy_chunks (id, doc_slug, doc_title, section, chunk_index, effective_date,
                                           content, content_hash, embedding_model, embedding, indexed_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10::vector, now())
                ON CONFLICT (id) DO UPDATE SET
                    doc_slug = EXCLUDED.doc_slug, doc_title = EXCLUDED.doc_title, section = EXCLUDED.section,
                    chunk_index = EXCLUDED.chunk_index, effective_date = EXCLUDED.effective_date,
                    content = EXCLUDED.content, content_hash = EXCLUDED.content_hash,
                    embedding_model = EXCLUDED.embedding_model, embedding = EXCLUDED.embedding,
                    indexed_at = now()
                """,
                chunk.id, chunk.doc_slug, chunk.doc_title, chunk.section, chunk.chunk_index, chunk.effective_date,
                chunk.content, chunk.content_hash(embedder.model), embedder.model, to_pgvector(vec),
            )
        if stale:
            await conn.execute("DELETE FROM policy_chunks WHERE id = ANY($1::text[])", stale)
    return IndexReport(len(chunks), len(todo), len(chunks) - len(todo), len(stale), tokens,
                       cost_usd(embedder.model, tokens))


async def search(pool, embedder: Embedder, query: str, top_k: int, threshold: float | None = None) -> tuple[list[dict], int]:
    """Top chunks by cosine similarity at or above the threshold, and the
    tokens spent embedding the query."""
    threshold = min_score() if threshold is None else threshold
    (vec,), tokens = await embedder.embed([query])
    rows = await pool.fetch(
        """
        SELECT doc_slug, doc_title, section, effective_date, content,
               1 - (embedding <=> $1::vector) AS score
        FROM policy_chunks
        WHERE embedding_model = $2
        ORDER BY embedding <=> $1::vector
        LIMIT $3
        """,
        to_pgvector(vec), embedder.model, top_k,
    )
    results = [
        {"doc_slug": r["doc_slug"], "doc_title": r["doc_title"], "section": r["section"],
         "effective_date": r["effective_date"].isoformat() if r["effective_date"] else None,
         "content": r["content"], "score": round(float(r["score"]), 4)}
        for r in rows if float(r["score"]) >= threshold
    ]
    return results, tokens
