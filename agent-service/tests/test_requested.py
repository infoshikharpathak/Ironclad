"""The deterministic 'did the user ask for this transfer?' check."""

import pytest
from garrison import NOT_AN_ACTION

from app.requested import amounts, is_requested_action


def transfer(amount, to="ACC-10043-CHK", name="Bob Smith", success=True):
    return {"tool": "initiate_transfer", "success": success, "tool_executed": True,
            "params": {"from_account": "acc_demo_user_checking", "to_account": to, "amount": amount},
            "response": {"transfer_id": "txn_1", "status": "pending_otp", "to_account": to, "to_name": name}}


def turn(user, *calls):
    return {"user": user, "reply": "", "tool_calls": list(calls)}


@pytest.mark.parametrize("text,expected", [
    ("send $50 to Bob", {50}), ("50 dollars", {50}), ("pay 50.00 now", {50}), ("$1,000 please", {1000}),
    ("pay Alice 120", {120}), ("$12.5 and $3", {12.5, 3}),
])
def test_amounts(text, expected):
    assert {float(a) for a in amounts(text)} == expected


def test_send_50_to_bob_matches():
    t = transfer(50)
    assert is_requested_action([], turn("send $50 to Bob for lunch", t), t) is True


@pytest.mark.parametrize("t", [transfer(500), transfer(50, "ACC-10042-CHK", "Alice Johnson")])
def test_wrong_amount_or_payee_is_not_requested(t):
    assert is_requested_action([], turn("send $50 to Bob for lunch", t), t) is False


def test_two_turn_request_with_a_yes():
    t = transfer(50)
    history = [{"user": "send Bob 50", "reply": "Should I send $50 to Bob Smith (ACC-10043-CHK)?", "tool_calls": []}]
    assert is_requested_action(history, turn("yes", t), t) is True


def test_yes_to_nothing_is_not_a_request():
    t = transfer(50)
    history = [{"user": "send Bob 50", "reply": "Bob Smith's account is ACC-10043-CHK.", "tool_calls": []}]
    assert is_requested_action(history, turn("yes", t), t) is False


def test_can_i_question_is_not_a_request():
    t = transfer(3000)
    assert is_requested_action([], turn("Can I send $3,000 to Bob today?", t), t) is False


def test_can_i_then_yes_is_a_request():
    t = transfer(3000)
    history = [{"user": "Can I send $3,000 to Bob today?", "reply": "Yes. Would you like me to start it?",
                "tool_calls": []}]
    assert is_requested_action(history, turn("yes please", t), t) is True


def test_withheld_response_in_the_turn_is_never_requested():
    t = transfer(50)
    withheld = {"tool": "lookup_account", "success": False, "tool_executed": True,
                "violation": "injection_detected_response"}
    assert is_requested_action([], turn("send $50 to Bob", withheld, t), t) is False


def test_move_to_savings_matches_the_own_account():
    t = transfer(200, "acc_demo_user_savings", "Savings")
    assert is_requested_action([], turn("move $200 to savings", t), t) is True


def test_reads_and_failed_starts_are_not_actions():
    assert is_requested_action([], turn("hi"), {"tool": "get_accounts", "success": True}) is NOT_AN_ACTION
    t = transfer(50, success=False)
    assert is_requested_action([], turn("send $50 to Bob", t), t) is NOT_AN_ACTION


def test_older_turns_dont_count():
    t = transfer(50)
    history = [{"user": "send $50 to Bob", "reply": "Done.", "tool_calls": []},
               {"user": "thanks", "reply": "You're welcome.", "tool_calls": []},
               {"user": "what's my balance?", "reply": "$9,950.", "tool_calls": []}]
    assert is_requested_action(history, turn("and again", t), t) is False
