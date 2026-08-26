from __future__ import annotations

import random
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from db import ensure_database, insert_customer, insert_event


SEED = 7
TOTAL_CUSTOMERS = 24
SUBSCRIPTION_FAILURES = 60
CHECKOUT_ABANDONMENTS = 40


def build_customers() -> list[dict]:
    rng = random.Random(SEED)
    customers = []
    languages = ["en", "en", "en", "hi"]
    for index in range(1, TOTAL_CUSTOMERS + 1):
        customers.append(
            {
                "customer_id": f"CUS_{index:04d}",
                "name": f"Customer {index}",
                "email": f"customer{index}@example.com",
                "phone": f"9{index:09d}"[-10:],
                "language_pref": rng.choice(languages),
                "opted_out": index in {3, 17},
                "total_attempts": 3 if index in {8, 14} else rng.randint(0, 2),
                "last_attempt_at": None,
                "created_at": datetime(2026, 8, 1, 10, 0, tzinfo=ZoneInfo("Asia/Kolkata")).isoformat(),
                "escalated": False,
            }
        )
    return customers


def build_events(customers: list[dict]) -> list[dict]:
    rng = random.Random(SEED)
    now = datetime(2026, 8, 20, 12, 0, tzinfo=ZoneInfo("Asia/Kolkata"))
    failure_codes = ["insufficient_funds", "card_expired", "bank_decline", "mandate_revoked"]
    checkout_stages = ["cart", "payment_method", "otp"]
    events = []

    for index in range(1, SUBSCRIPTION_FAILURES + 1):
        customer = rng.choice(customers)
        amount = rng.choice([49_900, 99_900, 199_900, 499_900, 999_900, 1_250_000])
        if index == 2:
            amount = 2_500_000
        events.append(
            {
                "event_id": f"SUB_{index:04d}",
                "event_type": "subscription_payment_failed",
                "customer_id": customer["customer_id"],
                "customer_name": customer["name"],
                "amount": amount,
                "currency": "INR",
                "attempt_number": rng.randint(1, 3),
                "failure_code": rng.choice(failure_codes),
                "checkout_stage": None,
                "time_spent_seconds": None,
                "customer_lang_pref": customer["language_pref"],
                "external_reference": f"sub_ref_{index:04d}",
                "created_at": (now - timedelta(hours=index)).isoformat(),
                "source": "synthetic",
            }
        )

    for index in range(1, CHECKOUT_ABANDONMENTS + 1):
        customer = rng.choice(customers)
        event_id = f"CHK_{index:04d}"
        external_reference = f"chk_ref_{index:04d}"
        if index in {4, 5}:
            external_reference = "chk_ref_duplicate_case"
        events.append(
            {
                "event_id": event_id,
                "event_type": "checkout_abandoned",
                "customer_id": customer["customer_id"],
                "customer_name": customer["name"],
                "amount": rng.choice([19_900, 49_900, 149_900, 399_900, 799_900]),
                "currency": "INR",
                "attempt_number": rng.randint(1, 3),
                "failure_code": None,
                "checkout_stage": rng.choice(checkout_stages),
                "time_spent_seconds": rng.choice([25, 45, 90, 180, 260]),
                "customer_lang_pref": customer["language_pref"],
                "external_reference": external_reference,
                "created_at": (now - timedelta(minutes=index * 37)).isoformat(),
                "source": "synthetic",
            }
        )
    return events


def main() -> None:
    ensure_database()
    customers = build_customers()
    for customer in customers:
        insert_customer(customer)
    for event in build_events(customers):
        insert_event(event)
    print("Synthetic data generation complete.")


if __name__ == "__main__":
    main()
