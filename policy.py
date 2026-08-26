from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from config import settings
from models import PolicyDecision


def is_quiet_hours(reference_time: str | None = None) -> bool:
    zone = ZoneInfo(settings.timezone_name)
    if reference_time:
        dt = datetime.fromisoformat(reference_time)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=zone)
        else:
            dt = dt.astimezone(zone)
    else:
        dt = datetime.now(zone)
    return dt.hour >= settings.quiet_hours_start or dt.hour < settings.quiet_hours_end


def enforce_amount_protection(original_amount: int, requested_amount: int) -> None:
    if requested_amount > original_amount:
        raise ValueError("Recovery amount cannot exceed original transaction amount.")


def evaluate_policy(
    *,
    diagnosis: str,
    confidence: float,
    amount: int,
    attempt_count: int,
    customer: dict,
    current_time: str | None = None,
    previous_action_status: str | None = None,
    already_recovered: bool = False,
) -> PolicyDecision:
    if already_recovered or previous_action_status == "paid":
        return PolicyDecision(False, "stop_no_action", "Payment already recovered.", False, "already_recovered")
    if amount > settings.autonomous_limit:
        return PolicyDecision(False, "escalate_to_human", "Amount exceeds autonomous recovery limit.", True, "high_value")
    if attempt_count >= settings.max_customer_attempts:
        return PolicyDecision(False, "escalate_to_human", "Maximum customer recovery attempts reached.", True, "max_attempts")
    if customer.get("opted_out"):
        return PolicyDecision(False, "stop_no_action", "Customer has opted out of contact.", False, "opt_out")
    if confidence < 0.60:
        return PolicyDecision(False, "escalate_to_human", "Diagnosis confidence is below autonomous threshold.", True, "low_confidence")
    if diagnosis == "unknown":
        return PolicyDecision(False, "stop_no_action", "Unknown diagnosis cannot trigger autonomous recovery.", False, "unknown_diagnosis")
    if is_quiet_hours(current_time):
        return PolicyDecision(False, "retry_scheduled", "Quiet hours in IST block customer contact action.", False, "quiet_hours")
    return PolicyDecision(True, "send_payment_link", "Recovery is within policy and amount limit.", False, "autonomous_recovery")
