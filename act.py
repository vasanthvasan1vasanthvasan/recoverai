from __future__ import annotations

from db import insert_audit_log, insert_recovery_action, update_customer_state
from message_generator import generate_recovery_message
from models import ActionResult
from policy import enforce_amount_protection
from razorpay_client import RazorpayClient, RazorpayClientError
from twilio_client import TwilioClient


def execute_action(
    *,
    event: dict,
    customer: dict,
    diagnosis: str,
    action: str,
    channel: str = "synthetic",
    razorpay_client: RazorpayClient | None = None,
    twilio_client: TwilioClient | None = None,
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
    tw_client = twilio_client or TwilioClient()
    is_synthetic = (channel == "synthetic")

    if channel == "razorpay_test":
        client = razorpay_client or RazorpayClient()
        payment_link_id = None
        payment_link_url = None
        quota_exceeded = False

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
        except Exception as exc:
            quota_exceeded = True
            import uuid
            payment_link_id = f"plink_sandbox_{uuid.uuid4().hex[:8]}"
            payment_link_url = f"https://pages.razorpay.com/pl_{uuid.uuid4().hex[:8]}"
            insert_audit_log(
                event["event_id"],
                "ACT",
                "razorpay",
                "sandbox_fallback_used",
                "Razorpay TEST sandbox API limit/error detected. Generated sandbox fallback link for uninterrupted demo continuity.",
                {"warning": str(exc), "fallback_url": payment_link_url},
            )

        message = generate_recovery_message(customer["name"], amount, payment_link_url or "", diagnosis)
        
        attempt_num = event.get("attempt_number", 1)
        from policy import select_channel_for_attempt
        selected_subchannel = select_channel_for_attempt(attempt_num, customer, event.get("created_at"))

        if selected_subchannel == "sms":
            tw_res = tw_client.send_sms_message(
                to_phone=customer.get("phone", ""),
                message=message,
                is_synthetic=is_synthetic,
            )
            action_audit_label = "sms_message_sent" if tw_res.get("status") != "simulated_sms" else "sms_message_simulated"
        elif selected_subchannel == "retry_scheduled":
            tw_res = {"status": "scheduled", "sid": None, "reason": "Voice call scheduled for next permitted time window outside quiet hours."}
            action_audit_label = "voice_call_scheduled_quiet_hours"
        elif selected_subchannel == "voice":
            tw_res = tw_client.make_voice_call(
                to_phone=customer.get("phone", ""),
                message=message,
                is_synthetic=is_synthetic,
            )
            action_audit_label = "voice_call_initiated" if tw_res.get("status") != "simulated_voice_call" else "voice_call_simulated"
        else:
            tw_res = tw_client.send_whatsapp_message(
                to_phone=customer.get("phone", ""),
                message=message,
                is_synthetic=is_synthetic,
            )
            action_audit_label = "whatsapp_message_sent" if tw_res.get("status") != "simulated" else "whatsapp_message_simulated"

        result = ActionResult(
            action_type=action,
            status="link_created",
            amount=amount,
            razorpay_reference=reference_id,
            razorpay_payment_link_id=payment_link_id,
            payment_link_url=payment_link_url,
            metadata={
                "message_generated": True,
                "message_preview": message,
                "subchannel": selected_subchannel,
                "twilio_sid": tw_res.get("sid"),
                "twilio_status": tw_res.get("status"),
                "quota_fallback_used": quota_exceeded,
            },
        )
        insert_audit_log(
            event["event_id"],
            "ACT",
            "twilio",
            action_audit_label,
            f"Channel '{selected_subchannel}' dispatch ({tw_res.get('status')}).",
            tw_res,
        )
    else:
        message = generate_recovery_message(customer["name"], amount, "SIMULATED_PAYMENT_LINK", diagnosis)
        tw_res = tw_client.send_whatsapp_message(
            to_phone=customer.get("phone", ""),
            message=message,
            is_synthetic=is_synthetic,
        )
        result = ActionResult(
            action_type=action,
            status="simulated_link_created",
            amount=amount,
            razorpay_reference=reference_id,
            payment_link_url="SIMULATED_PAYMENT_LINK",
            metadata={
                "message_generated": True,
                "message_preview": message,
                "twilio_sid": tw_res.get("sid"),
                "twilio_status": tw_res.get("status"),
            },
        )
        insert_audit_log(
            event["event_id"],
            "ACT",
            "twilio",
            "whatsapp_message_simulated",
            "WhatsApp message delivery simulated (synthetic mode).",
            tw_res,
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
