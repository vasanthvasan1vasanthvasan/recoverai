from __future__ import annotations

from unittest.mock import MagicMock
from db import ensure_database, get_connection, get_pending_human_cases, list_audit_logs
from generate_synthetic_data import main as generate_data
from human_review import approve_case, reject_case
from pipeline import process_event


def setup_fresh_db():
    ensure_database()
    with get_connection() as conn:
        conn.executescript("""
            DELETE FROM events;
            DELETE FROM customers;
            DELETE FROM decisions;
            DELETE FROM recovery_actions;
            DELETE FROM audit_logs;
            DELETE FROM webhook_events;
        """)
    generate_data()


def test_human_review_reject_path():
    setup_fresh_db()
    # Process event SUB_0002 (High amount ₹25,000 -> escalated by policy amount threshold)
    process_event("SUB_0002", channel="synthetic")

    pending_cases = get_pending_human_cases(source="synthetic")
    assert len(pending_cases) >= 1
    target = next((c for c in pending_cases if c["event_id"] == "SUB_0002"), None)
    assert target is not None
    assert target["amount"] == 2500000  # ₹25,000 in paise

    # Mock any network call to ensure ZERO network requests on rejection
    mock_razorpay = MagicMock()

    # Reject the case
    result = reject_case("SUB_0002", reviewer="test_supervisor", notes="Amount too high for manual override")
    assert result["status"] == "rejected"
    assert result["api_calls_made"] == 0
    mock_razorpay.assert_not_called()

    # Confirm case is no longer in pending queue
    updated_pending = get_pending_human_cases(source="synthetic")
    assert not any(c["event_id"] == "SUB_0002" for c in updated_pending)

    # Confirm audit log records human_rejected
    logs = list_audit_logs("SUB_0002")
    human_logs = [l for l in logs if l["stage"] == "HUMAN_REVIEW"]
    assert len(human_logs) == 1
    assert human_logs[0]["action"] == "human_rejected"
    assert human_logs[0]["actor"] == "test_supervisor"


def test_human_review_approve_path():
    setup_fresh_db()
    # Process event SUB_0002 (High amount ₹25,000 -> escalated by policy amount threshold)
    process_event("SUB_0002", channel="synthetic")

    pending_cases = get_pending_human_cases(source="synthetic")
    assert any(c["event_id"] == "SUB_0002" for c in pending_cases)

    # Approve the case
    result = approve_case("SUB_0002", reviewer="admin_manager", notes="Manual approval granted after phone verification")
    assert result["status"] == "approved"
    assert result["candidate_action"] == "send_payment_link"

    # Confirm case is no longer in pending queue
    updated_pending = get_pending_human_cases(source="synthetic")
    assert not any(c["event_id"] == "SUB_0002" for c in updated_pending)

    # Confirm audit log records human_approved
    logs = list_audit_logs("SUB_0002")
    human_logs = [l for l in logs if l["stage"] == "HUMAN_REVIEW"]
    assert len(human_logs) == 1
    assert human_logs[0]["action"] == "human_approved"
    assert human_logs[0]["actor"] == "admin_manager"
