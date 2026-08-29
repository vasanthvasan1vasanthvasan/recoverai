from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

import requests
from requests.auth import HTTPBasicAuth

from config import settings


class TwilioClientError(Exception):
    pass


@dataclass
class TwilioClient:
    account_sid: str | None = None
    auth_token: str | None = None
    whatsapp_number: str | None = None
    content_sid: str | None = None

    def __post_init__(self) -> None:
        if self.account_sid is None:
            self.account_sid = settings.twilio_account_sid
        if self.auth_token is None:
            self.auth_token = settings.twilio_auth_token
        if self.whatsapp_number is None:
            self.whatsapp_number = settings.twilio_whatsapp_number
        if self.content_sid is None:
            self.content_sid = settings.twilio_content_sid

    @property
    def is_configured(self) -> bool:
        return bool(self.account_sid and self.auth_token and self.whatsapp_number)

    def send_whatsapp_message(
        self,
        to_phone: str,
        message: str,
        *,
        is_synthetic: bool = True,
    ) -> dict[str, Any]:
        """Sends a WhatsApp message via Twilio Sandbox API for live interactive mode,

        or returns a simulated delivery payload for synthetic benchmark mode.
        """
        # Strict isolation: synthetic benchmark mode NEVER calls external API
        if is_synthetic or not self.is_configured:
            simulated_sid = f"SM_simulated_{uuid.uuid4().hex[:16]}"
            return {
                "status": "simulated",
                "sid": simulated_sid,
                "to": to_phone,
                "body": message,
                "error_code": None,
                "error_message": None,
            }

        # Format recipient phone number
        formatted_to = to_phone.strip()
        if not formatted_to.startswith("whatsapp:"):
            if not formatted_to.startswith("+"):
                formatted_to = f"+91{formatted_to}" if len(formatted_to) == 10 else f"+{formatted_to}"
            formatted_to = f"whatsapp:{formatted_to}"

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        payload: dict[str, Any] = {
            "From": self.whatsapp_number,
            "To": formatted_to,
            "Body": message,
        }
        if self.content_sid:
            payload["ContentSid"] = self.content_sid

        try:
            resp = requests.post(
                url,
                data=payload,
                auth=HTTPBasicAuth(self.account_sid, self.auth_token),
                timeout=10,
            )
            data = resp.json()
            if resp.status_code in (200, 201):
                return {
                    "status": data.get("status", "queued"),
                    "sid": data.get("sid"),
                    "to": formatted_to,
                    "body": message,
                    "error_code": None,
                    "error_message": None,
                }
            else:
                return {
                    "status": "failed",
                    "sid": data.get("sid"),
                    "to": formatted_to,
                    "body": message,
                    "error_code": str(data.get("code", resp.status_code)),
                    "error_message": str(data.get("message", "Twilio API error")),
                }
        except Exception as exc:
            return {
                "status": "failed",
                "sid": None,
                "to": formatted_to,
                "body": message,
                "error_code": "connection_error",
                "error_message": str(exc),
            }

    def send_sms_message(
        self,
        to_phone: str,
        message: str,
        *,
        is_synthetic: bool = True,
    ) -> dict[str, Any]:
        """Sends an SMS message via Twilio REST API for live mode or simulated for synthetic."""
        if is_synthetic or not self.is_configured:
            return {
                "status": "simulated_sms",
                "sid": f"SM_sms_{uuid.uuid4().hex[:16]}",
                "to": to_phone,
                "body": message,
                "error_code": None,
                "error_message": None,
            }
        formatted_to = to_phone.strip()
        if not formatted_to.startswith("+"):
            formatted_to = f"+91{formatted_to}" if len(formatted_to) == 10 else f"+{formatted_to}"

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Messages.json"
        from_num = self.whatsapp_number.replace("whatsapp:", "") if self.whatsapp_number else ""
        payload = {"From": from_num, "To": formatted_to, "Body": message}
        try:
            resp = requests.post(
                url, data=payload, auth=HTTPBasicAuth(self.account_sid, self.auth_token), timeout=10
            )
            data = resp.json()
            return {
                "status": data.get("status", "queued") if resp.status_code in (200, 201) else "failed",
                "sid": data.get("sid"),
                "to": formatted_to,
                "body": message,
                "error_code": None if resp.status_code in (200, 201) else str(data.get("code")),
                "error_message": None if resp.status_code in (200, 201) else str(data.get("message")),
            }
        except Exception as exc:
            return {"status": "failed", "sid": None, "to": formatted_to, "body": message, "error_code": "connection_error", "error_message": str(exc)}

    def make_voice_call(
        self,
        to_phone: str,
        message: str,
        *,
        is_synthetic: bool = True,
    ) -> dict[str, Any]:
        """Initiates an automated voice call via Twilio Voice API for live mode or simulated for synthetic."""
        if is_synthetic or not self.is_configured:
            return {
                "status": "simulated_voice_call",
                "sid": f"CA_voice_{uuid.uuid4().hex[:16]}",
                "to": to_phone,
                "twiml": f"<Response><Say>{message}</Say></Response>",
                "error_code": None,
                "error_message": None,
            }
        formatted_to = to_phone.strip()
        if not formatted_to.startswith("+"):
            formatted_to = f"+91{formatted_to}" if len(formatted_to) == 10 else f"+{formatted_to}"

        url = f"https://api.twilio.com/2010-04-01/Accounts/{self.account_sid}/Calls.json"
        from_num = self.whatsapp_number.replace("whatsapp:", "") if self.whatsapp_number else ""
        payload = {
            "From": from_num,
            "To": formatted_to,
            "Url": "https://webhooks.twilio.com/v1/Voice/Template/voice_speech_recognition",
        }
        try:
            resp = requests.post(
                url, data=payload, auth=HTTPBasicAuth(self.account_sid, self.auth_token), timeout=10
            )
            data = resp.json()
            return {
                "status": data.get("status", "queued") if resp.status_code in (200, 201) else "failed",
                "sid": data.get("sid"),
                "to": formatted_to,
                "twiml": twiml,
                "error_code": None if resp.status_code in (200, 201) else str(data.get("code")),
                "error_message": None if resp.status_code in (200, 201) else str(data.get("message")),
            }
        except Exception as exc:
            return {"status": "failed", "sid": None, "to": formatted_to, "body": message, "error_code": "connection_error", "error_message": str(exc)}
