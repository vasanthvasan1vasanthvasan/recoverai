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


def test_candidate_action_ranking():
    from diagnose import evaluate_candidate_actions
    from models import DiagnosisResult

    diag = DiagnosisResult(diagnosis="insufficient_funds", confidence=1.0, reasoning="Test", source="rules")
    candidates = evaluate_candidate_actions(
        {"amount": 99900, "failure_code": "insufficient_funds"},
        {"total_attempts": 0},
        diag,
    )
    assert len(candidates) == 4
    # Ranked by expected recovery value descending
    assert candidates[0].expected_recovery >= candidates[1].expected_recovery
    assert candidates[0].action == "send_payment_link"

