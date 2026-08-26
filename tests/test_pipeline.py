from __future__ import annotations

from pathlib import Path
from uuid import uuid4


def _project_temp_dir(prefix: str) -> Path:
    directory = Path(__file__).resolve().parent.parent / "test_tmp" / f"{prefix}-{uuid4().hex}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def test_pipeline_creates_decision(monkeypatch):
    tmp_dir = _project_temp_dir("pipeline")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_dir / "test.db"))

    from db import ensure_database, get_decision, insert_customer, insert_event
    from pipeline import process_event

    ensure_database()
    insert_customer(
        {
            "customer_id": "CUS_0001",
            "name": "Test Customer",
            "email": "test@example.com",
            "phone": "9999999999",
            "language_pref": "en",
            "opted_out": False,
            "total_attempts": 0,
        }
    )
    insert_event(
        {
            "event_id": "EVT_0001",
            "event_type": "subscription_payment_failed",
            "customer_id": "CUS_0001",
            "customer_name": "Test Customer",
            "amount": 99_900,
            "currency": "INR",
            "attempt_number": 1,
            "failure_code": "insufficient_funds",
            "created_at": "2026-08-20T14:00:00+05:30",
            "source": "synthetic",
        }
    )
    process_event("EVT_0001", channel="synthetic")
    decision = get_decision("EVT_0001")
    assert decision is not None
    assert decision["diagnosis"] == "insufficient_funds"
