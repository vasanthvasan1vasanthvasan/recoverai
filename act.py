from __future__ import annotations

from db import insert_audit_log, insert_recovery_action, update_customer_state
from message_generator import generate_recovery_message
from models import ActionResult
from policy import enforce_amount_protection
from razorpay_client import RazorpayClient, RazorpayClientError


def execute_action(
    *,
    event: dict,
    customer: dict,
    diagnosis: str,
    action: str,
    channel: str = "synthetic",
    razorpay_client: RazorpayClient | None = None,
) -> ActionResult:
    amount = int(event["amount"])
    enforce_amount_protection(amount, amount)

    if action in {"stop_no_action", "escalate_to_human", "retry_scheduled"}:
        status = "blocked" if action == "stop_no_action" else "pending_human" if action == "escalate_to_human" else "scheduled"
        result = ActionResult(action_type=action, status=status, amount=amount)
        insert_recovery_action(
            {
                "event_id": event["event_id"],
                "action_type": result.action_type,
                "status": result.status,
                "amount": result.amount,
                "attempt_number": event.get("attempt_number", 1),
                "channel": channel,
            }
        )
        if action == "escalate_to_human":
            update_customer_state(event["customer_id"], escalated=True)
        return result

    reference_id = f"RECOVERAI_{event['event_id']}"
    if channel == "razorpay_test":
        client = razorpay_client or RazorpayClient()
        try:
            response = client.create_payment_link(
                amount=amount,
                customer_name=customer["name"],
                customer_email=customer["email"],
                customer_phone=customer["phone"],
                reference_id=reference_id,
                description=f"Recovery for {event['event_id']}",
            )
            payment_link_id = response.get("id")
            payment_link_url = response.get("short_url") or response.get("invoice_url")
            message = generate_recovery_message(customer["name"], amount, payment_link_url or "", diagnosis)
            result = ActionResult(
                action_type=action,
                status="link_created",
                amount=amount,
                razorpay_reference=reference_id,
                razorpay_payment_link_id=payment_link_id,
                payment_link_url=payment_link_url,
                metadata={"message_generated": True, "message_preview": message},
            )
        except RazorpayClientError as exc:
            insert_audit_log(
                event["event_id"],
                "ACT",
                "system",
                "payment_link_failed",
                "Razorpay Payment Link creation failed.",
                {"error": str(exc)},
            )
            result = ActionResult(
                action_type=action,
                status="failed",
                amount=amount,
                razorpay_reference=reference_id,
                error_code="razorpay_error",
                error_message=str(exc),
            )
    else:
        message = generate_recovery_message(customer["name"], amount, "SIMULATED_PAYMENT_LINK", diagnosis)
        result = ActionResult(
            action_type=action,
            status="simulated_link_created",
            amount=amount,
            razorpay_reference=reference_id,
            payment_link_url="SIMULATED_PAYMENT_LINK",
            metadata={"message_generated": True, "message_preview": message},
        )

    insert_recovery_action(
        {
            "event_id": event["event_id"],
            "action_type": result.action_type,
            "status": result.status,
            "amount": result.amount,
            "razorpay_reference": result.razorpay_reference,
            "razorpay_payment_link_id": result.razorpay_payment_link_id,
            "payment_link_url": result.payment_link_url,
            "error_code": result.error_code,
            "error_message": result.error_message,
            "attempt_number": event.get("attempt_number", 1),
            "channel": channel,
        }
    )
    if result.status in {"link_created", "simulated_link_created"}:
        update_customer_state(event["customer_id"], increment_attempts=True)
    return result
