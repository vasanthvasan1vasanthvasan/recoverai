from __future__ import annotations

from typing import Any

from ai_client import AIClient, AIClientError
from models import ALLOWED_ABANDONMENT_DIAGNOSES, KNOWN_FAILURE_MAP, DiagnosisResult


def _unknown(reason: str, source: str) -> DiagnosisResult:
    return DiagnosisResult(diagnosis="unknown", confidence=0.0, reasoning=reason, source=source)


def validate_diagnosis_response(payload: dict[str, Any]) -> DiagnosisResult:
    diagnosis = payload.get("diagnosis")
    confidence = payload.get("confidence")
    reasoning = payload.get("reasoning")

    if diagnosis not in ALLOWED_ABANDONMENT_DIAGNOSES:
        return _unknown("Invalid diagnosis value from AI output.", "llm_validation")
    if not isinstance(confidence, (int, float)):
        return _unknown("Invalid confidence value from AI output.", "llm_validation")
    if not isinstance(reasoning, str) or not reasoning.strip():
        return _unknown("Invalid reasoning value from AI output.", "llm_validation")

    return DiagnosisResult(
        diagnosis=diagnosis,
        confidence=max(0.0, min(float(confidence), 1.0)),
        reasoning=reasoning.strip(),
        source="llm",
    )


def diagnose_event(event: dict[str, Any], customer: dict[str, Any], ai_client: AIClient | None = None) -> DiagnosisResult:
    failure_code = event.get("failure_code")
    if failure_code in KNOWN_FAILURE_MAP:
        return DiagnosisResult(
            diagnosis=KNOWN_FAILURE_MAP[failure_code],
            confidence=1.0,
            reasoning="Known payment failure code.",
            source="rules",
        )

    if event.get("event_type") == "checkout_abandoned":
        context = {
            "amount": event.get("amount"),
            "checkout_stage": event.get("checkout_stage"),
            "time_spent_seconds": event.get("time_spent_seconds"),
            "previous_attempts": customer.get("total_attempts", 0),
            "time_of_day": event.get("created_at"),
        }
        client = ai_client or AIClient()
        try:
            return validate_diagnosis_response(client.diagnose_abandonment(context))
        except AIClientError as exc:
            return _unknown(f"LLM diagnosis unavailable: {exc}", "llm_fallback")
        except Exception as exc:
            return _unknown(f"LLM diagnosis failed: {exc}", "llm_fallback")

    return _unknown("No matching diagnosis path.", "fallback")


def evaluate_candidate_actions(
    event: dict[str, Any],
    customer: dict[str, Any],
    diagnosis_result: DiagnosisResult,
) -> list[CandidateAction]:
    """Calculates probabilities and expected recovery values across candidate actions.

    Sorted by expected recovery value descending.
    """
    from models import CandidateAction

    amount = float(event.get("amount", 0) or 0)
    conf = diagnosis_result.confidence
    diag = diagnosis_result.diagnosis
    attempts = customer.get("total_attempts", 0)

    # 1. Payment Link + WhatsApp
    if diag in {"insufficient_funds", "payment_friction", "checkout_friction"}:
        link_prob = min(0.86, max(0.40, conf * 0.86))
        link_reason = "High conversion probability via Razorpay TEST Payment Link and WhatsApp dispatch."
    elif diag == "expired_card":
        link_prob = 0.72
        link_reason = "Payment link allows customer to update payment instrument quickly."
    else:
        link_prob = 0.50
        link_reason = "Standard payment link dispatch."

    # 2. Scheduled Retry
    if diag == "insufficient_funds":
        retry_prob = 0.55
        retry_reason = "Bank retry scheduled after fund buffer period."
    elif diag == "bank_decline":
        retry_prob = 0.40
        retry_reason = "Bank system cooldown retry."
    else:
        retry_prob = 0.25
        retry_reason = "Automated retry attempt."

    # 3. Human Escalation
    escalate_prob = 0.20 if attempts < 3 else 0.10
    escalate_reason = "Human review queue routing for high-touch intervention."

    # 4. Stop / No Action
    stop_prob = 0.0
    stop_reason = "No automated action."

    candidates = [
        CandidateAction(
            action="send_payment_link",
            probability=round(link_prob, 2),
            expected_recovery=round(amount * link_prob, 2),
            reason=link_reason,
        ),
        CandidateAction(
            action="retry_scheduled",
            probability=round(retry_prob, 2),
            expected_recovery=round(amount * retry_prob, 2),
            reason=retry_reason,
        ),
        CandidateAction(
            action="escalate_to_human",
            probability=round(escalate_prob, 2),
            expected_recovery=round(amount * escalate_prob, 2),
            reason=escalate_reason,
        ),
        CandidateAction(
            action="stop_no_action",
            probability=round(stop_prob, 2),
            expected_recovery=0.0,
            reason=stop_reason,
        ),
    ]

    candidates.sort(key=lambda c: c.expected_recovery, reverse=True)
    return candidates

