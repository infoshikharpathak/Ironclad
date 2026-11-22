"""The approval line: written by the system, not the model.

After initiate_transfer starts a transfer, the service adds a fixed line to
the reply, built only from fields of the structured tool result. It is added
after Anvil's output scan (the model didn't write it, so it isn't scanned)
and after any fallback, at most once per transfer.

Payee names come from the bank directory, where anyone can set their own, so
they are untrusted: control characters and markup are stripped and the name
is cut to NAME_MAX characters.

If Anvil withheld initiate_transfer's response (something in it looked like
an injection, e.g. the payee's name), the transfer may still exist and is now
suspicious: it is flagged, and the line leaves out every detail but the
amount (or, if the host can't read the result at all, every detail).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

NAME_MAX = 60
ACCOUNT_MAX = 40
_MARKUP = re.compile(r"<[^>]*>|[<>`*_~#|\[\]\\{}]")
_SPACES = re.compile(r"\s+")

WITHHELD_REASON = "response_withheld"


def clean(text: Any, limit: int) -> str:
    """*text* as inert plain text: no control or format characters, no
    markup, single spaces, at most *limit* characters (cut with '…')."""
    s = "".join(" " if unicodedata.category(ch).startswith(("C", "Z")) else ch for ch in str(text or ""))
    s = _SPACES.sub(" ", _MARKUP.sub("", s)).strip()
    return s if len(s) <= limit else s[: limit - 1].rstrip() + "…"


def money(amount: Any) -> str | None:
    try:
        return f"${float(amount):,.2f}"
    except (TypeError, ValueError):
        return None


_ACCOUNT = re.compile(r"[^A-Za-z0-9_\-]")


def approved_line(data: dict) -> str | None:
    amount = money(data.get("amount"))
    # Account IDs are the bank's own (ACC-10043-CHK, acc_demo_user_savings):
    # keep only ID characters, underscores included.
    account = _ACCOUNT.sub("", str(data.get("to_account") or ""))[:ACCOUNT_MAX]
    if amount is None or not account:
        return None
    name = clean(data.get("to_name"), NAME_MAX)
    if account.startswith("acc_") and name:  # the user's own account: "your Savings account"
        payee = f"your {name} account"
    else:
        payee = f"{name} ({account})" if name else account
    return (f"Transfer of {amount} to {payee} is waiting for your approval. "
            "Enter the OTP shown in your Ironclad app.")


def withheld_line(amount: str) -> str:
    return (f"A transfer of {amount} is waiting for your approval in your Ironclad app. Its details were "
            "withheld by a safety check, so review it carefully before approving.")


GENERIC_WITHHELD_LINE = ("A transfer may be waiting for your approval in your Ironclad app. "
                         "Review its details carefully before approving.")


def plan(tool_calls: list[dict]) -> tuple[list[str], list[str], bool]:
    """(lines, transfer IDs to flag as response_withheld, flag_recent) for a
    turn's initiate_transfer calls. flag_recent: a withheld start whose
    result the host can't read, so every pending transfer from this turn
    gets flagged at the bank."""
    lines: list[str] = []
    to_flag: list[str] = []
    seen: set[str] = set()
    flag_recent = False
    generic = False
    for call in tool_calls:
        if call.get("tool") != "initiate_transfer" or not call.get("tool_executed"):
            continue
        if call.get("success"):
            data = call.get("response") if isinstance(call.get("response"), dict) else {}
            tid = data.get("transfer_id")
            if data.get("status") != "pending_otp" or not tid or tid in seen:
                continue
            line = approved_line(data)
            if line:
                seen.add(tid)
                lines.append(line)
            continue
        if call.get("violation") not in ("injection_detected_response", "schema_violation"):
            continue  # failed or refused: nothing was started
        host = call.get("withheld_response") if isinstance(call.get("withheld_response"), dict) else None
        tid, amount = (host or {}).get("transfer_id"), money((host or {}).get("amount"))
        if host is not None and tid and amount and (host.get("status") in (None, "pending_otp")):
            if tid not in seen:
                seen.add(tid)
                to_flag.append(str(tid))
                lines.append(withheld_line(amount))
        else:
            flag_recent = True
            if not generic:
                generic = True
                lines.append(GENERIC_WITHHELD_LINE)
    return lines, to_flag, flag_recent


def append(reply: str, lines: list[str]) -> str:
    """The reply with each line added once (never twice, even if the model
    happened to write it)."""
    out = reply.rstrip()
    for line in lines:
        if line not in out:
            out = f"{out}\n\n{line}" if out else line
    return out
