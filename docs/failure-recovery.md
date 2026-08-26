# Failure Recovery & Resilience

## Implemented & Verified

- **LLM Fallback:** LLM unavailability or API key absence safely falls back to deterministic heuristic diagnosis without throwing runtime exceptions.
- **Invalid AI Output:** Malformed AI JSON response falls back to `unknown` diagnosis and triggers policy escalation to human.
- **Razorpay API Resilience:** Razorpay client calls handle network failures gracefully and record failure status in audit logs.
- **Idempotent Webhooks:** Duplicate webhook payloads are ignored using unique `external_event_id` tracking in the `webhook_events` table.
- **Webhook Security:** Invalid HMAC-SHA256 signatures are immediately rejected with HTTP 400 Bad Request.
- **Policy Protection:** Policy rejection prevents downstream Razorpay API execution whenever guardrails (quiet hours, opt-out, attempt caps, amount ceiling) fire.

## Verified Live Integration

- ✅ Real Razorpay TEST Payment Link creation (`create_payment_link`) verified with live SDK credentials.
- ✅ Live webhook signature verification (`verify_webhook_signature`) tested via built-in Webhook Simulator and Flask server.
- ✅ Dynamic database metric calculations and deduplicated SQL joining verified under pytest.
