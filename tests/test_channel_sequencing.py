from __future__ import annotations

from policy import evaluate_policy, select_channel_for_attempt


def test_channel_sequencing_attempts():
    customer = {"opted_out": False}
    # Attempt 1 -> whatsapp
    assert select_channel_for_attempt(1, customer, "2026-08-20T14:00:00+05:30") == "whatsapp"
    # Attempt 2 -> sms
    assert select_channel_for_attempt(2, customer, "2026-08-20T14:00:00+05:30") == "sms"
    # Attempt 3 (Daytime) -> voice
    assert select_channel_for_attempt(3, customer, "2026-08-20T14:00:00+05:30") == "voice"
    # Attempt 3 (Quiet Hours 22:00) -> retry_scheduled
    assert select_channel_for_attempt(3, customer, "2026-08-20T22:00:00+05:30") == "retry_scheduled"
    # Attempt >= 4 -> human
    assert select_channel_for_attempt(4, customer, "2026-08-20T14:00:00+05:30") == "human"


def test_opt_out_blocks_channel_selection():
    customer = {"opted_out": True}
    assert select_channel_for_attempt(1, customer) == "none"


def test_already_recovered_stops_future_attempts():
    decision = evaluate_policy(
        diagnosis="insufficient_funds",
        confidence=1.0,
        amount=99_900,
        attempt_count=1,
        customer={"opted_out": False},
        already_recovered=True,
    )
    assert decision.action == "stop_no_action"
    assert decision.rule_applied == "already_recovered"
