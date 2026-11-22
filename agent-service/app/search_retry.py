"""Retry an empty policy search with the user's own words (no LLM).

The model often shortens a question into a search query ("foreign
transaction fee", "send $6,000 to Alice") that falls under the bank's
"not covered" cut-off, while the user's own wording finds the section. If
search_policies comes back empty and the model's query differs from the
user's latest message, the service searches once more with that message (cut
to 300 characters, the tool's limit) before the model sees anything. The
retry goes through Anvil like any call, so it uses the same key and level
filter, and it is recorded in the trace with retried_with_user_text.
"""

from __future__ import annotations

from typing import Any

TOOL = "search_policies"
MAX_Q = 300


def _results(payload: dict) -> list | None:
    data = payload.get("data") if payload.get("success") else None
    return data.get("results") if isinstance(data, dict) else None


def _norm(text: str) -> str:
    return " ".join(text.lower().split())


async def retry_empty_search(ctx: Any, name: str, params: dict, payload: dict, *, user_message: str | None,
                             call_again) -> dict | None:
    if name != TOOL or _results(payload) != []:
        return None
    text = " ".join((user_message or "").split())[:MAX_Q]
    query = str(params.get("q") or "")
    if len(text) < 3 or _norm(text) == _norm(query):
        return None
    again = await call_again({**params, "q": text}, {"retried_with_user_text": True, "original_q": query})
    return again if _results(again) else None
