"""Chunking keeps each chunk's document and section."""

from datetime import date

from app.policies import chunking

DOC = """---
level: public
---

# Transfer Limits

Effective date: 2026-10-01

## Overview

Limits protect you.

## Transfers to other people

One. Two. Three. Four. Five. Six. Seven. Eight. Nine. Ten. Eleven. Twelve.
"""


def test_one_chunk_per_section_with_metadata():
    chunks = chunking.parse_document("transfer-limits", DOC)
    assert [(c.doc_slug, c.doc_title, c.section, c.chunk_index, c.effective_date) for c in chunks] == [
        ("transfer-limits", "Transfer Limits", "Overview", 0, date(2026, 10, 1)),
        ("transfer-limits", "Transfer Limits", "Transfers to other people", 0, date(2026, 10, 1)),
    ]
    assert chunks[1].id == "transfer-limits:transfers-to-other-people:0"
    assert chunks[0].embedding_text() == "Transfer Limits: Overview\n\nLimits protect you."


def test_long_sections_split_with_overlap_and_keep_their_section():
    chunks = chunking.parse_document("transfer-limits", DOC, max_tokens=6, overlap_tokens=2)
    split = [c for c in chunks if c.section == "Transfers to other people"]
    assert len(split) > 2 and [c.chunk_index for c in split] == list(range(len(split)))
    for a, b in zip(split, split[1:]):
        # the next piece starts with the last sentence(s) of the one before
        assert b.content.split()[0] in a.content.split()[-2:]
    assert all(c.doc_title == "Transfer Limits" and c.effective_date == date(2026, 10, 1) for c in split)
    assert " ".join(dict.fromkeys(" ".join(c.content for c in split).split())) == \
        "One. Two. Three. Four. Five. Six. Seven. Eight. Nine. Ten. Eleven. Twelve."


def test_content_hash_depends_on_text_and_model():
    (a, _) = chunking.parse_document("x", DOC)[:2]
    assert a.content_hash("m1") == a.content_hash("m1") != a.content_hash("m2")


def test_every_bank_policy_parses():
    chunks = chunking.load_policies()
    slugs = {c.doc_slug for c in chunks}
    assert len(slugs) == 14 and all(c.effective_date and c.doc_title and c.section for c in chunks)
    assert len({c.id for c in chunks}) == len(chunks)


def test_level_comes_from_front_matter_and_is_required():
    internal = DOC.replace("level: public", "level: internal")
    assert {c.level for c in chunking.parse_document("x", internal)} == {"internal"}
    import pytest
    for bad in (DOC.split("---\n\n", 1)[1], DOC.replace("level: public", "level: secret")):
        with pytest.raises(ValueError, match="front matter must set level"):
            chunking.parse_document("x", bad)


def test_bank_policies_have_public_and_internal_documents():
    levels = {}
    for c in chunking.load_policies():
        levels.setdefault(c.doc_slug, set()).add(c.level)
    assert all(len(v) == 1 for v in levels.values())  # every section shares its document's level
    internal = sorted(k for k, v in levels.items() if v == {"internal"})
    assert internal == ["account-freeze-criteria", "agent-guardrail-monitoring", "fraud-monitoring-thresholds",
                        "merchant-risk-rules"]
    assert len(levels) - len(internal) == 10
