from __future__ import annotations


def format_inr_paise(amount: int) -> str:
    return f"Rs. {amount / 100:.2f}"


def generate_recovery_message(customer_name: str, amount: int, payment_link: str, diagnosis: str) -> str:
    intro = "Your recent payment was not completed."
    if diagnosis == "price_friction":
        intro = "Your recent checkout was left incomplete."
    return (
        f"Hi {customer_name},\n\n"
        f"{intro}\n"
        f"You can securely complete your payment of {format_inr_paise(amount)} here:\n\n"
        f"{payment_link}\n\n"
        "If you have already paid, please ignore this message."
    )
