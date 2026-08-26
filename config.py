from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    timezone_name: str = "Asia/Kolkata"
    autonomous_limit: int = 1_000_000
    max_customer_attempts: int = 3
    quiet_hours_start: int = 21
    quiet_hours_end: int = 9

    @property
    def razorpay_key_id(self) -> str:
        return os.getenv("RAZORPAY_KEY_ID", "")

    @property
    def razorpay_key_secret(self) -> str:
        return os.getenv("RAZORPAY_KEY_SECRET", "")

    @property
    def razorpay_webhook_secret(self) -> str:
        return os.getenv("RAZORPAY_WEBHOOK_SECRET", "")

    @property
    def llm_api_key(self) -> str:
        return os.getenv("LLM_API_KEY", "")

    @property
    def database_path(self) -> str:
        return os.getenv("DATABASE_PATH", "data/recoverai.db")

    @property
    def database_file(self) -> Path:
        configured = Path(self.database_path)
        if configured.is_absolute():
            return configured
        return BASE_DIR / configured

    @property
    def razorpay_enabled(self) -> bool:
        return bool(self.razorpay_key_id and self.razorpay_key_secret)


settings = Settings()
