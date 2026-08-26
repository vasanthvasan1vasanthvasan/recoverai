from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from config import settings


class AIClientError(Exception):
    pass


@dataclass
class AIClient:
    api_key: str | None = None

    def __post_init__(self) -> None:
        if self.api_key is None:
            self.api_key = settings.llm_api_key

    def diagnose_abandonment(self, context: dict[str, Any]) -> dict[str, Any]:
        if not self.api_key:
            return self._heuristic_response(context)

        try:
            if self.api_key.startswith("AIza"):
                return self._call_gemini(context)
            elif self.api_key.startswith("sk-"):
                return self._call_openai(context)
            else:
                return self._call_gemini(context)
        except Exception:
            return self._heuristic_response(context)

    def _call_gemini(self, context: dict[str, Any]) -> dict[str, Any]:
        import requests

        url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={self.api_key}"
        prompt = (
            "You are an AI revenue recovery agent. Analyze this abandoned checkout context:\n"
            f"{json.dumps(context, indent=2)}\n\n"
            "Diagnose the cause of checkout abandonment. Return ONLY a JSON object with this exact schema:\n"
            "{\n"
            '  "diagnosis": "payment_friction" | "price_friction" | "checkout_friction" | "unknown",\n'
            '  "confidence": float between 0.0 and 1.0,\n'
            '  "reasoning": "short explanation"\n'
            "}"
        )
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"response_mime_type": "application/json"},
        }
        resp = requests.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"]
        return json.loads(text)

    def _call_openai(self, context: dict[str, Any]) -> dict[str, Any]:
        import requests

        url = "https://api.openai.com/v1/chat/completions"
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}
        prompt = (
            "You are an AI revenue recovery agent. Analyze this abandoned checkout context:\n"
            f"{json.dumps(context, indent=2)}\n\n"
            "Return ONLY a JSON object:\n"
            '{"diagnosis": "payment_friction"|"price_friction"|"checkout_friction"|"unknown", "confidence": float, "reasoning": "text"}'
        )
        payload = {
            "model": "gpt-4o-mini",
            "response_format": {"type": "json_object"},
            "messages": [{"role": "user", "content": prompt}],
        }
        resp = requests.post(url, headers=headers, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        text = data["choices"][0]["message"]["content"]
        return json.loads(text)

    def _heuristic_response(self, context: dict[str, Any]) -> dict[str, Any]:
        stage = context.get("checkout_stage")
        seconds = int(context.get("time_spent_seconds", 0) or 0)
        amount = int(context.get("amount", 0) or 0)
        attempts = int(context.get("previous_attempts", 0) or 0)

        if stage == "otp":
            return {
                "diagnosis": "payment_friction",
                "confidence": 0.86,
                "reasoning": "Customer reached payment confirmation stage but did not complete checkout.",
            }
        if stage == "payment_method" and amount > 300_000:
            return {
                "diagnosis": "price_friction",
                "confidence": 0.64,
                "reasoning": "Higher amount and abandonment at payment method selection suggest price sensitivity.",
            }
        if stage == "cart" and seconds < 60:
            return {
                "diagnosis": "checkout_friction",
                "confidence": 0.62,
                "reasoning": "Customer abandoned early in the flow, suggesting checkout friction.",
            }
        if attempts >= 3:
            return {
                "diagnosis": "unknown",
                "confidence": 0.45,
                "reasoning": "Previous attempts create ambiguity and reduce diagnosis confidence.",
            }
        return {
            "diagnosis": "payment_friction",
            "confidence": 0.66,
            "reasoning": "Customer reached a later checkout stage but did not complete payment.",
        }
