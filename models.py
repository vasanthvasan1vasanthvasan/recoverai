from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal


EventType = Literal["subscription_payment_failed", "checkout_abandoned"]
ActionType = Literal[
    "retry_now",
    "retry_scheduled",
    "send_payment_link",
    "escalate_to_human",
    "stop_no_action",
]

STAGES = ("DETECT", "DIAGNOSE", "DECIDE", "POLICY", "ACT", "TRACK", "REPORT")

KNOWN_FAILURE_MAP = {
    "insufficient_funds": "insufficient_funds",
    "card_expired": "expired_card",
    "bank_decline": "bank_decline",
    "mandate_revoked": "mandate_revoked",
}

ALLOWED_ABANDONMENT_DIAGNOSES = {
    "payment_friction",
    "price_friction",
    "checkout_friction",
    "unknown",
}








CONTACT_ACTIONS = {"send_payment_link", "retry_now"}


@dataclass
class DiagnosisResult:
    diagnosis: str
    confidence: float
    reasoning: str
    source: str


@dataclass
class CandidateAction:
    action: str
    probability: float
    expected_recovery: float
    reason: str


@dataclass
class PolicyDecision:
    allowed: bool
    action: str
    reason: str
    requires_human: bool
    rule_applied: str


@dataclass
class ActionResult:
    action_type: str
    status: str
    amount: int
    razorpay_reference: str | None = None
    razorpay_payment_link_id: str | None = None
    payment_link_url: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] | None = None

