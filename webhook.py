from __future__ import annotations

import json
from http import HTTPStatus
from typing import Any

from flask import Flask, jsonify, request

from config import settings
from db import insert_audit_log, insert_webhook_event, mark_webhook_processed
from razorpay_client import RazorpayClient
from track import record_outcome


app = Flask(__name__)


def extract_external_event_id(payload: dict[str, Any]) -> str:
    return str(
        payload.get("event_id")
        or payload.get("payload", {}).get("payment_link", {}).get("entity", {}).get("id")
        or ""
    )


def process_payment_link_paid(payload: dict[str, Any]) -> None:
    payment_link = payload.get("payload", {}).get("payment_link", {}).get("entity", {})
    reference_id = payment_link.get("reference_id", "")
    if not reference_id.startswith("RECOVERAI_"):
        return
    event_id = reference_id.replace("RECOVERAI_", "", 1)
    amount = int(payment_link.get("amount") or 0)
    record_outcome(event_id=event_id, outcome="paid", amount_recovered=amount, audit_reason="RAZORPAY TEST MODE")
    insert_audit_log(event_id, "TRACK", "webhook", "payment_link_paid", "Confirmed paid webhook received.", {"payment_link_id": payment_link.get("id")})


def handle_webhook(raw_body: str, signature: str, client: RazorpayClient | None = None) -> tuple[dict[str, Any], int]:
    razorpay_client = client or RazorpayClient()
    if not settings.razorpay_webhook_secret:
        return {"status": "error", "message": "Webhook secret not configured."}, HTTPStatus.INTERNAL_SERVER_ERROR
    if not razorpay_client.verify_webhook_signature(raw_body, signature, settings.razorpay_webhook_secret):
        return {"status": "error", "message": "Invalid signature."}, HTTPStatus.BAD_REQUEST

    payload = json.loads(raw_body)
    event_type = str(payload.get("event", ""))
    external_event_id = extract_external_event_id(payload)
    if not external_event_id:
        return {"status": "error", "message": "Missing external event id."}, HTTPStatus.BAD_REQUEST

    created = insert_webhook_event(external_event_id, event_type, payload, True)
    if not created:
        return {"status": "duplicate", "message": "Duplicate webhook ignored."}, HTTPStatus.OK

    if event_type == "payment_link.paid":
        process_payment_link_paid(payload)

    mark_webhook_processed(external_event_id)
    return {"status": "processed", "event_type": event_type}, HTTPStatus.OK


@app.post("/webhooks/razorpay")
def razorpay_webhook():
    raw_body = request.get_data(as_text=True)
    signature = request.headers.get("X-Razorpay-Signature", "")
    body, status = handle_webhook(raw_body, signature)
    return jsonify(body), status


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=False)
