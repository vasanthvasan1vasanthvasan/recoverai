from __future__ import annotations

from collections import Counter
from typing import Any

from db import fetch_all


def compute_metrics(channel: str | None = None) -> dict[str, Any]:
    where_clause = ""
    params: tuple[Any, ...] = ()
    if channel:
        where_clause = "WHERE ra.channel = ?"
        params = (channel,)

    rows = fetch_all(
        f"""
        SELECT e.event_id, e.amount, e.event_type, d.action_chosen, d.outcome, d.amount_recovered, d.policy_allowed,
               d.diagnosis, ra.status, ra.channel
        FROM events e
        LEFT JOIN decisions d ON d.event_id = e.event_id
        LEFT JOIN (
            SELECT event_id, status, channel, MAX(created_at) AS created_at
            FROM recovery_actions
            GROUP BY event_id
        ) ra ON ra.event_id = e.event_id
        {where_clause}
        """,
        params,
    )

    total_events = len(rows)
    revenue_at_risk = sum(int(row["amount"] or 0) for row in rows)
    recovery_attempts = sum(1 for row in rows if row["action_chosen"] == "send_payment_link")
    successful_recoveries = sum(1 for row in rows if row["outcome"] in {"paid", "simulated_success"})
    amount_recovered = sum(int(row["amount_recovered"] or 0) for row in rows)
    escalations = sum(1 for row in rows if row["action_chosen"] == "escalate_to_human")
    blocked_actions = sum(1 for row in rows if row["action_chosen"] == "stop_no_action")
    failed_actions = sum(1 for row in rows if row["outcome"] in {"failed", "simulated_no_recovery"})
    recovery_rate = (amount_recovered / revenue_at_risk * 100) if revenue_at_risk else 0.0
    escalation_rate = (escalations / total_events * 100) if total_events else 0.0

    return {
        "total_events": total_events,
        "revenue_at_risk": revenue_at_risk,
        "recovery_attempts": recovery_attempts,
        "successful_recoveries": successful_recoveries,
        "amount_recovered": amount_recovered,
        "recovery_rate": recovery_rate,
        "escalation_count": escalations,
        "escalation_rate": escalation_rate,
        "blocked_action_count": blocked_actions,
        "stopped_action_count": blocked_actions,
        "failed_action_count": failed_actions,
        "diagnosis_distribution": dict(Counter(row["diagnosis"] or "unprocessed" for row in rows)),
        "action_distribution": dict(Counter(row["action_chosen"] or "unprocessed" for row in rows)),
        "outcome_distribution": dict(Counter(row["outcome"] or "unprocessed" for row in rows)),
        "event_type_distribution": dict(Counter(row["event_type"] or "unknown" for row in rows)),
    }
