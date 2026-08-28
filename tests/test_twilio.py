from unittest.mock import MagicMock, patch

from act import execute_action
from config import settings
from twilio_client import TwilioClient


def test_twilio_synthetic_mode_is_simulated() -> None:
    client = TwilioClient(account_sid="AC123", auth_token="token", whatsapp_number="whatsapp:+14155238886")
    res = client.send_whatsapp_message("+919876543210", "Hello Test", is_synthetic=True)
    assert res["status"] == "simulated"
    assert res["sid"].startswith("SM_simulated_")
    assert res["error_code"] is None


def test_twilio_unconfigured_is_simulated() -> None:
    client = TwilioClient(account_sid="", auth_token="", whatsapp_number="")
    res = client.send_whatsapp_message("+919876543210", "Hello Test", is_synthetic=False)
    assert res["status"] == "simulated"
    assert res["sid"].startswith("SM_simulated_")


@patch("requests.post")
def test_twilio_live_mode_calls_api(mock_post: MagicMock) -> None:
    mock_post.return_value.status_code = 201
    mock_post.return_value.json.return_value = {
        "sid": "SM_live_123456789",
        "status": "queued",
        "code": None,
        "message": None,
    }

    client = TwilioClient(account_sid="ACtest", auth_token="tokentest", whatsapp_number="whatsapp:+14155238886")
    res = client.send_whatsapp_message("+919087823504", "Live Payment Recovery Link", is_synthetic=False)

    assert mock_post.called
    assert res["status"] == "queued"
    assert res["sid"] == "SM_live_123456789"
    assert res["to"] == "whatsapp:+919087823504"


def test_act_execute_action_populates_twilio_metadata() -> None:
    event = {
        "event_id": "TEST_EVT_TW1",
        "event_type": "subscription_payment_failed",
        "customer_id": "CUS_TW1",
        "amount": 50000,
        "created_at": "2026-08-28T10:00:00",
    }
    customer = {
        "customer_id": "CUS_TW1",
        "name": "Test Customer",
        "email": "test@example.com",
        "phone": "9876543210",
        "total_attempts": 0,
    }

    result = execute_action(
        event=event,
        customer=customer,
        diagnosis="payment_friction",
        action="retry_with_discount",
        channel="synthetic",
    )

    assert result.metadata["twilio_status"] == "simulated"
    assert result.metadata["twilio_sid"].startswith("SM_simulated_")
