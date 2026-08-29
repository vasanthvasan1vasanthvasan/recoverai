from __future__ import annotations

from dataclasses import asdict

from act import execute_action
from ai_client import AIClient
from db import get_customer, get_event, get_latest_action, insert_audit_log, upsert_decision
from diagnose import diagnose_event
from policy import evaluate_policy
from simulate_response import simulate_outcome
from track import record_outcome


def process_event(event_id: str, channel: str = "synthetic") -> dict:
    event = get_event(event_id)
    if not event:
        raise ValueError(f"Event not found: {event_id}")
    customer = get_customer(event["customer_id"])
    if not customer:
        raise ValueError(f"Customer not found: {event['customer_id']}")

    insert_audit_log(event_id, "DETECT", "system", "event_loaded", "Revenue-risk event loaded.", {"event_type": event["event_type"]})

    diagnosis = diagnose_event(event, customer, AIClient())
    insert_audit_log(event_id, "DIAGNOSE", "system", "diagnosis_complete", diagnosis.reasoning, asdict(diagnosis))

    previous_action = get_latest_action(event_id)
    prior_status = previous_action["status"] if previous_action else None
    policy = evaluate_policy(
        diagnosis=diagnosis.diagnosis,
        confidence=diagnosis.confidence,
        amount=event["amount"],
        attempt_count=int(customer["total_attempts"] or 0),
        customer=customer,
        current_time=event["created_at"],
        previous_action_status=prior_status,
    )
    insert_audit_log(event_id, "POLICY", "system", "policy_evaluated", policy.reason, asdict(policy))

    upsert_decision(
        {
            "event_id": event_id,
            "diagnosis": diagnosis.diagnosis,
            "diagnosis_confidence": diagnosis.confidence,
            "diagnosis_reasoning": diagnosis.reasoning,
            "action_chosen": policy.action,
            "action_reasoning": policy.reason,
            "policy_allowed": policy.allowed,
            "policy_rule_applied": policy.rule_applied,
            "requires_human": policy.requires_human,
            "outcome": "pending",
            "amount_recovered": 0,
        }
    )

    action_result = execute_action(
        event=event,
        customer=customer,
        diagnosis=diagnosis.diagnosis,
        action=policy.action,
        channel=channel,
    )
    insert_audit_log(event_id, "ACT", "system", action_result.action_type, action_result.status, action_result.metadata or {})

    if channel == "synthetic" and action_result.status in {"link_created", "simulated_link_created"}:
        simulation = simulate_outcome(event_id, diagnosis.diagnosis, int(event["amount"]))
        record_outcome(
            event_id=event_id,
            outcome=str(simulation["outcome"]),
            amount_recovered=int(simulation["amount_recovered"]),
            audit_reason=str(simulation["label"]),
        )
    elif action_result.status in {"blocked", "pending_human", "scheduled", "failed"}:
        mapped_outcome = {
            "blocked": "blocked",
            "pending_human": "escalated",
            "scheduled": "scheduled",
            "failed": "failed",
        }[action_result.status]
        record_outcome(event_id=event_id, outcome=mapped_outcome, amount_recovered=0, audit_reason="No confirmed recovery yet.")

    insert_audit_log(event_id, "REPORT", "system", "case_processed", "Pipeline completed.", {"channel": channel})
    return {
        "event": event,
        "customer": customer,
        "diagnosis": asdict(diagnosis),
        "policy": asdict(policy),
        "action": asdict(action_result),
    }


def process_all_events(channel: str = "synthetic") -> list[dict]:
    from db import fetch_all

    rows = fetch_all("SELECT event_id FROM events ORDER BY created_at ASC")
    return [process_event(row["event_id"], channel=channel) for row in rows]
