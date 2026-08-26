from __future__ import annotations

from db import ensure_database
from pipeline import process_all_events
from report import compute_metrics


def main() -> None:
    ensure_database()
    process_all_events(channel="synthetic")
    metrics = compute_metrics(channel="synthetic")
    for key, value in metrics.items():
        if isinstance(value, dict):
            continue
        print(f"{key}: {value}")


if __name__ == "__main__":
    main()
