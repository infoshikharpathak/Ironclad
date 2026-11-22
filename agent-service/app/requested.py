"""Did the user ask for this transfer? A deterministic check (no LLM).

bastion asks it when the output classifier labels a reply
unrequested_action. A transfer counts as requested only if, in the user's
messages of this turn and the previous 2:

- Amount: the transfer amount equals an amount the user wrote ("$50",
  "50 dollars", "50.00", "$1,000", "pay Alice 120").
- Payee: the user named the payee: the directory name, first name or
  account number (case-insensitive); for the user's own accounts, "savings"
  or "checking".

and this turn is a request, not a question: "can I...?" turns don't count,
and a bare "yes" counts only if the agent's previous reply asked whether to
go ahead. A turn with a withheld or flagged tool response is never
requested, so injected turns always keep the warning.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any

from bastion import NOT_AN_ACTION

TOOL = "initiate_transfer"
LOOKBACK = 2  # previous turns whose user messages count

_AMOUNT = re.compile(r"(?<![\w.])\$?\s?(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d{1,2}))?(?![\d,])")
_QUESTION = re.compile(r"^\s*(?:can|could|am|may|is it possible|would it be possible|do i have)\b", re.I)
_YES = re.compile(r"^\s*(?:yes|yeah|yep|sure|ok(?:ay)?|go ahead|do it|please do|confirm(?:ed)?|that'?s right|correct)\b",
                  re.I)
_OFFER = re.compile(r"\b(?:should i|shall i|would you like me to|do you want me to|want me to|"
                    r"would you like to proceed|shall we|should we)\b", re.I)
_WITHHELD = {"injection_detected_response", "schema_violation"}
_OWN_WORDS = {"checking": ("checking",), "savings": ("savings", "saving")}


def amounts(text: str) -> set[Decimal]:
    out = set()
    for whole, cents in _AMOUNT.findall(text or ""):
        try:
            out.add(Decimal(whole.replace(",", "") + ("." + cents if cents else "")))
        except InvalidOperation:
            continue
    return out


def _names(call: dict) -> list[str]:
    """Ways the user could have named the payee: account number, directory
    name, first name; for own accounts, the account type."""
    params = call.get("params") or {}
    data = call.get("response") if isinstance(call.get("response"), dict) else {}
    account = str(params.get("to_account") or data.get("to_account") or "")
    out = [account] if account else []
    if account.startswith("acc_"):  # the user's own account: acc_demo_user_savings
        for kind, words in _OWN_WORDS.items():
            if account.endswith(kind):
                out += list(words)
        return out
    name = str(data.get("to_name") or "").strip()
    if name:
        out += [name, name.split()[0]]
    return out


def _named(text: str, names: list[str]) -> bool:
    text = (text or "").lower()
    return any(re.search(rf"(?<!\w){re.escape(n.lower())}(?!\w)", text) for n in names if n)


def is_requested_action(history: list[dict[str, Any]], turn: dict[str, Any], action: dict[str, Any]):
    if action.get("tool") != TOOL:
        return NOT_AN_ACTION
    if not action.get("success"):
        return NOT_AN_ACTION  # nothing was started
    if any(c.get("violation") in _WITHHELD for c in turn.get("tool_calls") or []):
        return False  # something in this turn was withheld: keep the warning
    user = turn.get("user") or ""
    if _QUESTION.search(user):
        return False  # "can I...?" asks, it doesn't request
    recent = history[-LOOKBACK:]
    if _YES.search(user) and not (recent and _OFFER.search(recent[-1].get("reply") or "")):
        return False  # a bare yes to nothing
    texts = [t.get("user") or "" for t in recent if not _QUESTION.search(t.get("user") or "") or _YES.search(user)]
    texts.append(user)
    params = action.get("params") or {}
    try:
        amount = Decimal(str(params.get("amount")))
    except InvalidOperation:
        return False
    wrote_amount = any(amount in amounts(t) for t in texts)
    named_payee = any(_named(t, _names(action)) for t in texts)
    return wrote_amount and named_payee
