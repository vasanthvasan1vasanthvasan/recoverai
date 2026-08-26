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
