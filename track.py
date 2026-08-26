from __future__ import annotations

from db import insert_audit_log, update_recovery_action_status, upsert_decision, utcnow_iso


def record_outcome(*, event_id: str, outcome: str, amount_recovered: int = 0, audit_reason: str = "") -> None:
    upsert_decision(
        {
            "event_id": event_id,
            "executed_at": utcnow_iso(),
            "outcome": outcome,
            "amount_recovered": amount_recovered,
        }
    )
    if outcome in {"paid", "simulated_success"}:
        update_recovery_action_status(event_id, "paid", utcnow_iso())
    elif outcome in {"failed", "simulated_no_recovery"}:
        update_recovery_action_status(event_id, "failed", utcnow_iso())
    insert_audit_log(event_id, "TRACK", "system", outcome, audit_reason or "Outcome recorded.", {"amount_recovered": amount_recovered})
