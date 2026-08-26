from __future__ import annotations

from ai_client import AIClient
from diagnose import diagnose_event, validate_diagnosis_response


def test_known_failure_uses_rules():
    result = diagnose_event(
        {"event_type": "subscription_payment_failed", "failure_code": "insufficient_funds"},
        {"total_attempts": 0},
    )
    assert result.diagnosis == "insufficient_funds"
    assert result.confidence == 1.0
    assert result.source == "rules"


def test_invalid_ai_output_falls_back_to_unknown():
    result = validate_diagnosis_response({"diagnosis": "bad", "confidence": "oops", "reasoning": ""})
    assert result.diagnosis == "unknown"
    assert result.confidence == 0.0


def test_checkout_abandonment_llm_path():
    result = diagnose_event(
        {
            "event_type": "checkout_abandoned",
            "checkout_stage": "otp",
            "time_spent_seconds": 180,
            "amount": 99_900,
            "created_at": "2026-08-20T14:00:00+05:30",
        },
        {"total_attempts": 0},
        AIClient(api_key="dummy"),
    )
    assert result.diagnosis == "payment_friction"
