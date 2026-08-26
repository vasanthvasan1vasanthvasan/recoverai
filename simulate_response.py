from __future__ import annotations

import random


RECOVERY_PROBABILITIES = {
    "insufficient_funds": 0.42,
    "expired_card": 0.18,
    "bank_decline": 0.24,
    "mandate_revoked": 0.14,
    "payment_friction": 0.39,
    "price_friction": 0.21,
    "checkout_friction": 0.28,
    "unknown": 0.05,
}


def simulate_outcome(event_id: str, diagnosis: str, amount: int) -> dict[str, object]:
    probability = RECOVERY_PROBABILITIES.get(diagnosis, 0.05)
    seed = sum(ord(char) for char in f"{event_id}:{diagnosis}:{amount}")
    rng = random.Random(seed)
    recovered = rng.random() < probability
    return {
        "outcome": "simulated_success" if recovered else "simulated_no_recovery",
        "amount_recovered": amount if recovered else 0,
        "label": "SIMULATED OUTCOME",
    }
