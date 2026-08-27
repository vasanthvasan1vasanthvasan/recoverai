from __future__ import annotations

from dataclasses import asdict
from typing import Any

from act import execute_action
from db import (
    fetch_one,
    get_customer,
    get_event,
    insert_audit_log,
    update_human_review_record,
)
from simulate_response import simulate_outcome
from track import record_outcome


def approve_case(
    event_id: str,
    reviewer: str = "human_operator",
    notes: str = "",
    razorpay_client: Any | None = None,
) -> dict[str, Any]:
    event = get_event(event_id)
    if not event:
        raise ValueError(f"Event not found: {event_id}")
    customer = get_customer(event["customer_id"])
    if not customer:
        raise ValueError(f"Customer not found: {event['customer_id']}")

    decision = fetch_one("SELECT * FROM decisions WHERE event_id = ?", (event_id,))
    if not decision:
        raise ValueError(f"Decision record not found for event: {event_id}")

    # Determine original candidate action recommended by DECIDE
    candidate_action = decision["action_chosen"]
    if candidate_action == "escalate_to_human":
        candidate_action = "send_payment_link"

    channel = event.get("source", "synthetic")

    # Execute exact candidate action using existing act.py execute_action logic
    action_result = execute_action(
        event=event,
        customer=customer,
        diagnosis=decision["diagnosis"] or "unknown",
        action=candidate_action,
        channel=channel,
        razorpay_client=razorpay_client,
    )

    insert_audit_log(
        event_id,
        "HUMAN_REVIEW",
        reviewer,
        "human_approved",
        f"Human reviewer ({reviewer}) approved candidate action: {candidate_action}",
        {"notes": notes, "action_result": asdict(action_result)},
    )

    if channel == "synthetic" and action_result.status == "simulated_link_created":
        simulation = simulate_outcome(event_id, decision["diagnosis"] or "unknown", int(event["amount"]))
        record_outcome(
            event_id=event_id,
            outcome=str(simulation["outcome"]),
            amount_recovered=int(simulation["amount_recovered"]),
            audit_reason=f"Human approved ({reviewer}): {notes}",
        )
        final_outcome = str(simulation["outcome"])
    elif action_result.status == "link_created":
        final_outcome = "link_created"
        record_outcome(
            event_id=event_id,
            outcome="link_created",
            amount_recovered=0,
            audit_reason=f"Human approved payment link creation ({reviewer}): {notes}",
        )
    else:
        final_outcome = action_result.status

    update_human_review_record(
        event_id=event_id,
        human_status="approved",
        reviewer=reviewer,
        notes=notes,
        new_outcome=final_outcome,
    )

    return {
        "status": "approved",
        "candidate_action": candidate_action,
        "action_result": asdict(action_result),
        "final_outcome": final_outcome,
    }


def reject_case(
    event_id: str,
    reviewer: str = "human_operator",
    notes: str = "",
) -> dict[str, Any]:
    event = get_event(event_id)
    if not event:
        raise ValueError(f"Event not found: {event_id}")

    # ZERO API / NETWORK CALLS EXECUTED ON REJECTION
    insert_audit_log(
        event_id,
        "HUMAN_REVIEW",
        reviewer,
        "human_rejected",
        f"Human reviewer ({reviewer}) rejected recovery action.",
        {"notes": notes, "api_calls_made": 0},
    )

    record_outcome(
        event_id=event_id,
        outcome="stopped",
        amount_recovered=0,
        audit_reason=f"Human rejected recovery action ({reviewer}): {notes}",
    )

    update_human_review_record(
        event_id=event_id,
        human_status="rejected",
        reviewer=reviewer,
        notes=notes,
        new_outcome="stopped",
    )

    return {
        "status": "rejected",
        "event_id": event_id,
        "api_calls_made": 0,
        "final_outcome": "stopped",
    }
