from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Callable

from config import settings

try:
    import razorpay
except Exception:  # pragma: no cover
    razorpay = None


class RazorpayClientError(Exception):
    pass


@dataclass
class RazorpayClient:
    key_id: str | None = None
    key_secret: str | None = None
    max_retries: int = 2
    backoff_seconds: float = 0.5

    def __post_init__(self) -> None:
        if self.key_id is None:
            self.key_id = settings.razorpay_key_id
        if self.key_secret is None:
            self.key_secret = settings.razorpay_key_secret
        self._client = None
        if self.key_id and self.key_secret and razorpay is not None:
            self._client = razorpay.Client(auth=(self.key_id, self.key_secret))

    @property
    def enabled(self) -> bool:
        return self._client is not None

    def create_payment_link(
        self,
        *,
        amount: int,
        customer_name: str,
        customer_email: str,
        customer_phone: str,
        reference_id: str,
        description: str,
    ) -> dict[str, Any]:
        payload = {
            "amount": amount,
            "currency": "INR",
            "accept_partial": False,
            "reference_id": reference_id,
            "description": description,
            "customer": {
                "name": customer_name,
                "email": customer_email,
                "contact": customer_phone,
            },
            "notify": {"sms": False, "email": False},
            "reminder_enable": False,
        }
        return self._with_retry(lambda: self._require_client().payment_link.create(data=payload))

    def fetch_payment_link(self, payment_link_id: str) -> dict[str, Any]:
        return self._with_retry(lambda: self._require_client().payment_link.fetch(payment_link_id))

    def cancel_payment_link(self, payment_link_id: str) -> dict[str, Any]:
        return self._with_retry(lambda: self._require_client().payment_link.cancel(payment_link_id))

    def verify_webhook_signature(self, body: str, signature: str, secret: str) -> bool:
        client = self._require_client()
        try:
            client.utility.verify_webhook_signature(body, signature, secret)
            return True
        except Exception:
            return False

    def generate_webhook_signature(self, body: str, secret: str) -> str:
        import hashlib
        import hmac

        return hmac.new(secret.encode("utf-8"), body.encode("utf-8"), hashlib.sha256).hexdigest()

    def _require_client(self):
        if self._client is None:
            raise RazorpayClientError("Razorpay TEST credentials or SDK are not available.")
        return self._client

    def _with_retry(self, fn: Callable[[], dict[str, Any]]) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                return fn()
            except Exception as exc:
                last_error = exc
                if attempt >= self.max_retries:
                    break
                time.sleep(self.backoff_seconds * (attempt + 1))
        raise RazorpayClientError(str(last_error))
