from __future__ import annotations

import json
from db import ensure_database, fetch_all, get_customer, get_event, get_latest_action, insert_customer, insert_event
from pipeline import process_event
from razorpay_client import RazorpayClient
from webhook import handle_webhook
from policy import evaluate_policy, select_channel_for_attempt


def test_complete_e2e_recovery_journey():
    ensure_database()
    
    event_id = "E2E_EVT_001"
    customer_id = "E2E_CUS_001"
    amount = 99900  # ₹999.00

    insert_customer({
        "customer_id": customer_id,
        "name": "End2End Test User",
        "email": "e2e@example.com",
        "phone": "+919087823504",
        "language_pref": "en",
        "opted_out": False,
        "total_attempts": 0,
    })

    insert_event({
        "event_id": event_id,
        "event_type": "subscription_payment_failed",
        "customer_id": customer_id,
        "customer_name": "End2End Test User",
        "amount": amount,
        "currency": "INR",
        "attempt_number": 1,
        "failure_code": "insufficient_funds",
        "created_at": "2026-08-20T14:00:00+05:30",
        "source": "synthetic",
    })

    # Step 1: Attempt 1 -> WhatsApp
    cust = get_customer(customer_id)
    chan1 = select_channel_for_attempt(1, cust, "2026-08-20T14:00:00+05:30")
    assert chan1 == "whatsapp"

    res1 = process_event(event_id, channel="synthetic")
    assert res1["action"]["status"] == "simulated_link_created"

    # Step 2: Attempt 2 -> SMS
    cust = get_customer(customer_id)
    chan2 = select_channel_for_attempt(2, cust, "2026-08-20T14:00:00+05:30")
    assert chan2 == "sms"

    # Step 3: Attempt 3 -> Voice (Daytime)
    chan3 = select_channel_for_attempt(3, cust, "2026-08-20T14:00:00+05:30")
    assert chan3 == "voice"

    # Step 4: Razorpay payment_link.paid webhook arrives
    payload = {
        "event": "payment_link.paid",
        "payload": {
            "payment_link": {
                "entity": {
                    "id": "plink_e2e_123",
                    "reference_id": f"RECOVERAI_{event_id}",
                    "amount": amount,
                }
            }
        },
    }
    raw_body = json.dumps(payload)
    secret = "secret"
    client = RazorpayClient(key_id="test", key_secret="test")
    sig = client.generate_webhook_signature(raw_body, secret)

    body, status_code = handle_webhook(raw_body, sig, client=client)
    assert status_code == 200
    assert body.get("status") == "processed"

    # Step 5: Verify case status is recovered & future attempts are BLOCKED
    cust_updated = get_customer(customer_id)
    policy_after_pay = evaluate_policy(
        diagnosis="insufficient_funds",
        confidence=1.0,
        amount=amount,
        attempt_count=2,
        customer=cust_updated,
        already_recovered=True,
    )
    assert policy_after_pay.action == "stop_no_action"
    assert policy_after_pay.allowed is False
    assert policy_after_pay.rule_applied == "already_recovered"

    # Step 6: Verify audit trail entries exist for every lifecycle stage
    logs = fetch_all("SELECT stage FROM audit_logs WHERE event_id = ?", (event_id,))
    stages = {row["stage"] for row in logs}
    assert "DETECT" in stages
    assert "DIAGNOSE" in stages
    assert "POLICY" in stages
    assert "ACT" in stages
    assert "REPORT" in stages
