from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4


class StubClient:
    def __init__(self, valid: bool = True):
        self.valid = valid

    def verify_webhook_signature(self, body: str, signature: str, secret: str) -> bool:
        return self.valid and signature == "valid"


def _project_temp_dir(prefix: str) -> Path:
    directory = Path(__file__).resolve().parent.parent / "test_tmp" / f"{prefix}-{uuid4().hex}"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def test_extract_external_event_id():
    from webhook import extract_external_event_id

    payload = {
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {
                "entity": {"id": "plink_test", "reference_id": "RECOVERAI_EVT_001", "amount": 99_900}
            }
        },
    }
    assert extract_external_event_id(payload) == "plink_test"


def test_invalid_signature_rejected(monkeypatch):
    tmp_dir = _project_temp_dir("webhooks-invalid")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_dir / "webhooks.db"))
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "secret")
    from db import ensure_database
    from webhook import handle_webhook

    ensure_database()
    payload = json.dumps({"event": "payment_link.paid", "payload": {"payment_link": {"entity": {"id": "plink_x"}}}})
    body, status = handle_webhook(payload, "invalid", client=StubClient(valid=False))
    assert status == 400
    assert body["message"] == "Invalid signature."


def test_duplicate_event_ignored(monkeypatch):
    tmp_dir = _project_temp_dir("webhooks-duplicate")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_dir / "webhooks.db"))
    monkeypatch.setenv("RAZORPAY_WEBHOOK_SECRET", "secret")
    from db import ensure_database
    from webhook import handle_webhook

    ensure_database()
    payload = json.dumps({"event": "payment_link.paid", "payload": {"payment_link": {"entity": {"id": "plink_x"}}}})
    first_body, first_status = handle_webhook(payload, "valid", client=StubClient(valid=True))
    second_body, second_status = handle_webhook(payload, "valid", client=StubClient(valid=True))
    assert first_status == 200
    assert second_status == 200
    assert second_body["status"] == "duplicate"
