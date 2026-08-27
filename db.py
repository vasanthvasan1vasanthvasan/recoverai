from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Iterable

from config import settings


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def ensure_database() -> None:
    settings.database_file.parent.mkdir(parents=True, exist_ok=True)
    with get_connection() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS customers (
                customer_id TEXT PRIMARY KEY,
                name TEXT,
                email TEXT,
                phone TEXT,
                language_pref TEXT,
                opted_out BOOLEAN,
                total_attempts INTEGER,
                last_attempt_at DATETIME,
                created_at DATETIME,
                escalated BOOLEAN DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                event_type TEXT,
                customer_id TEXT,
                customer_name TEXT,
                amount INTEGER,
                currency TEXT,
                attempt_number INTEGER,
                failure_code TEXT NULL,
                checkout_stage TEXT NULL,
                time_spent_seconds INTEGER NULL,
                customer_lang_pref TEXT,
                external_reference TEXT NULL,
                created_at DATETIME,
                source TEXT DEFAULT 'synthetic'
            );

            CREATE TABLE IF NOT EXISTS decisions (
                decision_id TEXT PRIMARY KEY,
                event_id TEXT UNIQUE,
                diagnosis TEXT,
                diagnosis_confidence REAL,
                diagnosis_reasoning TEXT,
                action_chosen TEXT,
                action_reasoning TEXT,
                policy_allowed BOOLEAN,
                policy_rule_applied TEXT,
                requires_human BOOLEAN,
                executed_at DATETIME,
                outcome TEXT,
                amount_recovered INTEGER DEFAULT 0,
                human_review_status TEXT DEFAULT 'pending',
                human_reviewer TEXT NULL,
                human_reviewed_at DATETIME NULL,
                human_notes TEXT NULL
            );

            CREATE TABLE IF NOT EXISTS recovery_actions (
                action_id TEXT PRIMARY KEY,
                event_id TEXT,
                action_type TEXT,
                status TEXT,
                amount INTEGER,
                razorpay_reference TEXT NULL,
                razorpay_payment_link_id TEXT NULL,
                payment_link_url TEXT NULL,
                error_code TEXT NULL,
                error_message TEXT NULL,
                attempt_number INTEGER,
                channel TEXT DEFAULT 'synthetic',
                created_at DATETIME,
                completed_at DATETIME NULL
            );

            CREATE TABLE IF NOT EXISTS webhook_events (
                webhook_id TEXT PRIMARY KEY,
                external_event_id TEXT UNIQUE,
                event_type TEXT,
                payload TEXT,
                signature_valid BOOLEAN,
                processed BOOLEAN,
                received_at DATETIME,
                processed_at DATETIME NULL
            );

            CREATE TABLE IF NOT EXISTS audit_logs (
                audit_id TEXT PRIMARY KEY,
                event_id TEXT,
                stage TEXT,
                actor TEXT,
                action TEXT,
                reason TEXT,
                metadata TEXT,
                timestamp DATETIME
            );
            """
        )
        cursor = conn.cursor()
        cursor.execute("PRAGMA table_info(decisions)")
        columns = [column[1] for column in cursor.fetchall()]
        if "human_review_status" not in columns:
            cursor.execute("ALTER TABLE decisions ADD COLUMN human_review_status TEXT DEFAULT 'pending'")
        if "human_reviewer" not in columns:
            cursor.execute("ALTER TABLE decisions ADD COLUMN human_reviewer TEXT NULL")
        if "human_reviewed_at" not in columns:
            cursor.execute("ALTER TABLE decisions ADD COLUMN human_reviewed_at DATETIME NULL")
        if "human_notes" not in columns:
            cursor.execute("ALTER TABLE decisions ADD COLUMN human_notes TEXT NULL")


@contextmanager
def get_connection() -> Iterable[sqlite3.Connection]:
    settings.database_file.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(settings.database_file)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def fetch_one(query: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
    with get_connection() as conn:
        return conn.execute(query, params).fetchone()


def fetch_all(query: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
    with get_connection() as conn:
        return conn.execute(query, params).fetchall()


def insert_customer(customer: dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR REPLACE INTO customers
            (customer_id, name, email, phone, language_pref, opted_out, total_attempts, last_attempt_at, created_at, escalated)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                customer["customer_id"],
                customer["name"],
                customer["email"],
                customer["phone"],
                customer["language_pref"],
                int(customer.get("opted_out", False)),
                customer.get("total_attempts", 0),
                customer.get("last_attempt_at"),
                customer.get("created_at", utcnow_iso()),
                int(customer.get("escalated", False)),
            ),
        )


def insert_event(event: dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO events
            (event_id, event_type, customer_id, customer_name, amount, currency, attempt_number, failure_code,
             checkout_stage, time_spent_seconds, customer_lang_pref, external_reference, created_at, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                event["event_id"],
                event["event_type"],
                event["customer_id"],
                event["customer_name"],
                event["amount"],
                event.get("currency", "INR"),
                event.get("attempt_number", 1),
                event.get("failure_code"),
                event.get("checkout_stage"),
                event.get("time_spent_seconds"),
                event.get("customer_lang_pref", "en"),
                event.get("external_reference"),
                event.get("created_at", utcnow_iso()),
                event.get("source", "synthetic"),
            ),
        )


def upsert_decision(payload: dict[str, Any]) -> None:
    current = get_decision(payload["event_id"]) or {}
    merged = {**current, **payload}
    merged.setdefault("decision_id", current.get("decision_id", str(uuid.uuid4())))
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO decisions
            (decision_id, event_id, diagnosis, diagnosis_confidence, diagnosis_reasoning, action_chosen,
             action_reasoning, policy_allowed, policy_rule_applied, requires_human, executed_at, outcome, amount_recovered)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(event_id) DO UPDATE SET
                diagnosis=excluded.diagnosis,
                diagnosis_confidence=excluded.diagnosis_confidence,
                diagnosis_reasoning=excluded.diagnosis_reasoning,
                action_chosen=excluded.action_chosen,
                action_reasoning=excluded.action_reasoning,
                policy_allowed=excluded.policy_allowed,
                policy_rule_applied=excluded.policy_rule_applied,
                requires_human=excluded.requires_human,
                executed_at=excluded.executed_at,
                outcome=excluded.outcome,
                amount_recovered=excluded.amount_recovered
            """,
            (
                merged["decision_id"],
                merged["event_id"],
                merged.get("diagnosis"),
                merged.get("diagnosis_confidence"),
                merged.get("diagnosis_reasoning"),
                merged.get("action_chosen"),
                merged.get("action_reasoning"),
                int(bool(merged.get("policy_allowed", False))),
                merged.get("policy_rule_applied"),
                int(bool(merged.get("requires_human", False))),
                merged.get("executed_at"),
                merged.get("outcome"),
                merged.get("amount_recovered", 0),
            ),
        )


def get_decision(event_id: str) -> dict[str, Any] | None:
    row = fetch_one("SELECT * FROM decisions WHERE event_id = ?", (event_id,))
    return dict(row) if row else None


def insert_recovery_action(payload: dict[str, Any]) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO recovery_actions
            (action_id, event_id, action_type, status, amount, razorpay_reference, razorpay_payment_link_id,
             payment_link_url, error_code, error_message, attempt_number, channel, created_at, completed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.get("action_id", str(uuid.uuid4())),
                payload["event_id"],
                payload["action_type"],
                payload["status"],
                payload["amount"],
                payload.get("razorpay_reference"),
                payload.get("razorpay_payment_link_id"),
                payload.get("payment_link_url"),
                payload.get("error_code"),
                payload.get("error_message"),
                payload.get("attempt_number", 1),
                payload.get("channel", "synthetic"),
                payload.get("created_at", utcnow_iso()),
                payload.get("completed_at"),
            ),
        )


def update_recovery_action_status(
    event_id: str,
    status: str,
    completed_at: str | None = None,
    error_code: str | None = None,
    error_message: str | None = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE recovery_actions
            SET status = ?, completed_at = ?, error_code = COALESCE(?, error_code), error_message = COALESCE(?, error_message)
            WHERE event_id = ?
            """,
            (status, completed_at, error_code, error_message, event_id),
        )


def insert_webhook_event(
    external_event_id: str,
    event_type: str,
    payload: dict[str, Any],
    signature_valid: bool,
) -> bool:
    with get_connection() as conn:
        try:
            conn.execute(
                """
                INSERT INTO webhook_events
                (webhook_id, external_event_id, event_type, payload, signature_valid, processed, received_at, processed_at)
                VALUES (?, ?, ?, ?, ?, 0, ?, NULL)
                """,
                (
                    str(uuid.uuid4()),
                    external_event_id,
                    event_type,
                    json.dumps(payload),
                    int(signature_valid),
                    utcnow_iso(),
                ),
            )
            return True
        except sqlite3.IntegrityError:
            return False


def mark_webhook_processed(external_event_id: str) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE webhook_events
            SET processed = 1, processed_at = ?
            WHERE external_event_id = ?
            """,
            (utcnow_iso(), external_event_id),
        )


def insert_audit_log(
    event_id: str,
    stage: str,
    actor: str,
    action: str,
    reason: str,
    metadata: dict[str, Any] | None = None,
) -> None:
    with get_connection() as conn:
        conn.execute(
            """
            INSERT INTO audit_logs
            (audit_id, event_id, stage, actor, action, reason, metadata, timestamp)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid.uuid4()),
                event_id,
                stage,
                actor,
                action,
                reason,
                json.dumps(metadata or {}),
                utcnow_iso(),
            ),
        )


def get_event(event_id: str) -> dict[str, Any] | None:
    row = fetch_one("SELECT * FROM events WHERE event_id = ?", (event_id,))
    return dict(row) if row else None


def get_customer(customer_id: str) -> dict[str, Any] | None:
    row = fetch_one("SELECT * FROM customers WHERE customer_id = ?", (customer_id,))
    return dict(row) if row else None


def get_latest_action(event_id: str) -> dict[str, Any] | None:
    row = fetch_one(
        "SELECT * FROM recovery_actions WHERE event_id = ? ORDER BY created_at DESC LIMIT 1",
        (event_id,),
    )
    return dict(row) if row else None


def update_customer_state(customer_id: str, increment_attempts: bool = False, escalated: bool | None = None) -> None:
    customer = get_customer(customer_id)
    if not customer:
        return
    total_attempts = int(customer["total_attempts"] or 0) + (1 if increment_attempts else 0)
    escalated_value = customer["escalated"] if escalated is None else int(bool(escalated))
    with get_connection() as conn:
        conn.execute(
            """
            UPDATE customers
            SET total_attempts = ?, last_attempt_at = ?, escalated = ?
            WHERE customer_id = ?
            """,
            (total_attempts, utcnow_iso(), escalated_value, customer_id),
        )


def list_cases(source: str | None = None) -> list[dict[str, Any]]:
    where_clause = ""
    params: tuple[Any, ...] = ()
    if source:
        where_clause = "WHERE e.source = ?"
        params = (source,)

    rows = fetch_all(
        f"""
        SELECT
            e.event_id,
            e.customer_name,
            e.customer_id,
            e.event_type,
            e.amount,
            e.currency,
            e.created_at,
            e.source,
            d.diagnosis,
            d.diagnosis_confidence,
            d.diagnosis_reasoning,
            d.action_chosen,
            d.policy_allowed,
            d.policy_rule_applied,
            d.action_reasoning,
            d.outcome,
            d.amount_recovered,
            ra.status,
            ra.razorpay_reference,
            ra.razorpay_payment_link_id,
            ra.payment_link_url,
            ra.channel
        FROM events e
        LEFT JOIN decisions d ON d.event_id = e.event_id
        LEFT JOIN (
            SELECT ra1.*
            FROM recovery_actions ra1
            INNER JOIN (
                SELECT event_id, MAX(created_at) AS max_created_at
                FROM recovery_actions
                GROUP BY event_id
            ) ra2 ON ra1.event_id = ra2.event_id AND ra1.created_at = ra2.max_created_at
        ) ra ON ra.event_id = e.event_id
        {where_clause}
        ORDER BY e.created_at DESC
        """,
        params,
    )
    return [dict(row) for row in rows]


def list_audit_logs(event_id: str | None = None) -> list[dict[str, Any]]:
    if event_id:
        rows = fetch_all("SELECT * FROM audit_logs WHERE event_id = ? ORDER BY timestamp ASC", (event_id,))
    else:
        rows = fetch_all("SELECT * FROM audit_logs ORDER BY timestamp ASC")
    return [dict(row) for row in rows]


def get_pending_human_cases(source: str | None = None) -> list[dict[str, Any]]:
    ensure_database()
    where_clauses = ["(d.outcome = 'escalated' OR d.requires_human = 1 OR d.action_chosen = 'escalate_to_human')"]
    where_clauses.append("(d.human_review_status IS NULL OR d.human_review_status = 'pending')")
    params: list[Any] = []
    if source:
        where_clauses.append("e.source = ?")
        params.append(source)

    where_str = " WHERE " + " AND ".join(where_clauses)

    rows = fetch_all(
        f"""
        SELECT
            e.event_id,
            e.customer_name,
            e.customer_id,
            e.event_type,
            e.amount,
            e.currency,
            e.created_at,
            e.source,
            d.diagnosis,
            d.diagnosis_confidence,
            d.diagnosis_reasoning,
            d.action_chosen,
            d.policy_allowed,
            d.policy_rule_applied,
            d.action_reasoning,
            d.outcome,
            d.amount_recovered,
            d.human_review_status,
            d.human_reviewer,
            d.human_reviewed_at,
            d.human_notes,
            c.email as customer_email,
            c.phone as customer_phone
        FROM events e
        JOIN decisions d ON d.event_id = e.event_id
        LEFT JOIN customers c ON c.customer_id = e.customer_id
        {where_str}
        ORDER BY e.created_at DESC
        """,
        tuple(params),
    )
    return [dict(row) for row in rows]


def update_human_review_record(
    event_id: str,
    human_status: str,
    reviewer: str = "human_operator",
    notes: str = "",
    new_outcome: str | None = None,
) -> None:
    now = utcnow_iso()
    with get_connection() as conn:
        cursor = conn.cursor()
        updates = ["human_review_status = ?", "human_reviewer = ?", "human_reviewed_at = ?", "human_notes = ?"]
        params = [human_status, reviewer, now, notes]
        if new_outcome is not None:
            updates.append("outcome = ?")
            params.append(new_outcome)

        params.append(event_id)
        cursor.execute(
            f"UPDATE decisions SET {', '.join(updates)} WHERE event_id = ?",
            tuple(params),
        )

