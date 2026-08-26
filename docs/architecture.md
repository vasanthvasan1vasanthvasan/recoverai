# Architecture

RecoverAI uses a compact local architecture built for reliability and measurability.

## Pipeline

1. Revenue-risk events are stored in `events`.
2. `pipeline.py` loads the event and current customer state.
3. `diagnose.py` performs deterministic failure-code diagnosis or guarded LLM diagnosis.
4. `policy.py` enforces hard rules and chooses one bounded action.
5. `act.py` records a synthetic action or calls Razorpay Payment Links in TEST mode.
6. `track.py` records outcomes only after simulation or confirmed webhook input.
7. `report.py` computes metrics from the database.
8. `app.py` reads the stored data into a Streamlit interface.

## Data Model

- `customers`: persistent customer state for stop rules
- `events`: revenue-risk events
- `decisions`: diagnosis, policy, and tracked outcome
- `recovery_actions`: action execution details and Razorpay references
- `webhook_events`: idempotent external event storage
- `audit_logs`: chronological audit trail across the shared pipeline

## Razorpay Integration

All Razorpay interactions are isolated in `razorpay_client.py`:

- create Payment Link
- fetch Payment Link
- cancel Payment Link
- verify webhook signature

This keeps payment-integration concerns away from diagnosis, policy, and reporting logic.
