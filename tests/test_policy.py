from __future__ import annotations

from policy import enforce_amount_protection, evaluate_policy


BASE_CUSTOMER = {"opted_out": False}


def test_maximum_attempts_escalates():
    decision = evaluate_policy(
        diagnosis="insufficient_funds",
        confidence=1.0,
        amount=99_900,
        attempt_count=3,
        customer=BASE_CUSTOMER,
        current_time="2026-08-20T14:00:00+05:30",
    )
    assert decision.action == "escalate_to_human"


def test_opted_out_customer_stops():
    decision = evaluate_policy(
        diagnosis="payment_friction",
        confidence=0.9,
        amount=49_900,
        attempt_count=1,
        customer={"opted_out": True},
        current_time="2026-08-20T14:00:00+05:30",
    )
    assert decision.action == "stop_no_action"


def test_high_value_transaction_escalates():
    decision = evaluate_policy(
        diagnosis="insufficient_funds",
        confidence=1.0,
        amount=1_500_000,
        attempt_count=1,
        customer=BASE_CUSTOMER,
        current_time="2026-08-20T14:00:00+05:30",
    )
    assert decision.action == "escalate_to_human"


def test_quiet_hours_schedule_retry():
    decision = evaluate_policy(
        diagnosis="insufficient_funds",
        confidence=1.0,
        amount=99_900,
        attempt_count=1,
        customer=BASE_CUSTOMER,
        current_time="2026-08-20T22:00:00+05:30",
    )
    assert decision.action == "retry_scheduled"


def test_low_confidence_escalates():
    decision = evaluate_policy(
        diagnosis="payment_friction",
        confidence=0.4,
        amount=49_900,
        attempt_count=1,
        customer=BASE_CUSTOMER,
        current_time="2026-08-20T14:00:00+05:30",
    )
    assert decision.action == "escalate_to_human"


def test_amount_protection_raises():
    try:
        enforce_amount_protection(99_900, 199_900)
    except ValueError:
        return
    assert False, "Expected ValueError"


def test_already_recovered_stops():
    decision = evaluate_policy(
        diagnosis="insufficient_funds",
        confidence=1.0,
        amount=99_900,
        attempt_count=1,
        customer=BASE_CUSTOMER,
        current_time="2026-08-20T14:00:00+05:30",
        already_recovered=True,
    )
    assert decision.action == "stop_no_action"
