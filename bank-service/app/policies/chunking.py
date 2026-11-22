"""Split policy markdown into chunks, one per ## section, with long sections
split at about `max_tokens` with a little overlap. Every chunk keeps its
document's slug, title and effective date, and its section name."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

POLICIES_DIR = Path(__file__).resolve().parents[2] / "policies"

# Token counts are estimated (about 4 characters per token for English),
# which is close enough for sizing chunks and avoids a tokenizer dependency.
CHARS_PER_TOKEN = 4
# Chosen with evals/policies: 60-token chunks (most sections become 1-3
# chunks) beat whole sections (400) on recall@3, 0.90 vs 0.85.
DEFAULT_MAX_TOKENS = 60
DEFAULT_OVERLAP_TOKENS = 10

_EFFECTIVE = re.compile(r"^Effective date:\s*(\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)


@dataclass(frozen=True)
class Chunk:
    doc_slug: str
    doc_title: str
    section: str
    chunk_index: int
    effective_date: date | None
    content: str

    @property
    def id(self) -> str:
        return f"{self.doc_slug}:{slugify(self.section)}:{self.chunk_index}"

    def embedding_text(self) -> str:
        """What gets embedded: the title and section give the content context."""
        return f"{self.doc_title}: {self.section}\n\n{self.content}"

    def content_hash(self, model: str) -> str:
        return hashlib.sha256(f"{model}\n{self.embedding_text()}".encode()).hexdigest()


def estimate_tokens(text: str) -> int:
    return max(1, len(text) // CHARS_PER_TOKEN)


def slugify(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


def parse_document(slug: str, markdown: str, *, max_tokens: int = DEFAULT_MAX_TOKENS,
                   overlap_tokens: int = DEFAULT_OVERLAP_TOKENS) -> list[Chunk]:
    title_match = re.search(r"^# (.+)$", markdown, re.MULTILINE)
    if title_match is None:
        raise ValueError(f"policy {slug!r} has no '# Title' line")
    title = title_match.group(1).strip()
    eff = _EFFECTIVE.search(markdown)
    effective = date.fromisoformat(eff.group(1)) if eff else None

    chunks: list[Chunk] = []
    for section, body in _sections(markdown):
        for i, piece in enumerate(split_text(body, max_tokens, overlap_tokens)):
            chunks.append(Chunk(slug, title, section, i, effective, piece))
    return chunks


def load_policies(directory: Path = POLICIES_DIR, **kwargs) -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(directory.glob("*.md")):
        chunks += parse_document(path.stem, path.read_text(), **kwargs)
    return chunks


def _sections(markdown: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    parts = re.split(r"^## (.+)$", markdown, flags=re.MULTILINE)
    # parts = [preamble, name1, body1, name2, body2, ...]
    for name, body in zip(parts[1::2], parts[2::2]):
        body = body.strip()
        if body:
            out.append((name.strip(), body))
    return out


def split_text(text: str, max_tokens: int, overlap_tokens: int) -> list[str]:
    """Split at sentence boundaries into pieces of at most ~max_tokens; each
    piece after the first starts with the last ~overlap_tokens of the one
    before it."""
    if estimate_tokens(text) <= max_tokens:
        return [text]
    sentences = re.split(r"(?<=[.!?])\s+", text)
    pieces: list[str] = []
    current: list[str] = []
    for sentence in sentences:
        candidate = " ".join(current + [sentence])
        if current and estimate_tokens(candidate) > max_tokens:
            pieces.append(" ".join(current))
            carry: list[str] = []
            for s in reversed(current):  # whole sentences, up to the overlap budget
                if estimate_tokens(" ".join([s] + carry)) > overlap_tokens:
                    break
                carry.insert(0, s)
            current = carry + [sentence]
        else:
            current.append(sentence)
    if current:
        pieces.append(" ".join(current))
    return pieces
