"""Explicit environment configuration for the VPS-resident LINE Bot."""

from __future__ import annotations

import os
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_UP
from pathlib import Path


MICROUSD_PER_USD = 1_000_000


def usd_to_microusd(value: str, name: str) -> int:
    """Parse a positive USD environment value without floating-point drift."""

    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError(f"{name} must be a decimal USD amount.") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError(f"{name} must be greater than zero.")
    return int((amount * MICROUSD_PER_USD).to_integral_value(rounding=ROUND_UP))


@dataclass(frozen=True)
class BotSettings:
    channel_secret: str
    channel_access_token: str
    allowed_group_ids: frozenset[str]
    bot_user_id: str
    pos_base_url: str
    pos_shared_secret: str
    data_root: Path
    port: int = 8010
    retry_seconds: int = 300
    enrollment_mode: bool = False
    vision_product_group_ids: frozenset[str] = frozenset()
    gemini_api_key: str = ""
    gemini_model: str = ""
    gemini_timeout_seconds: int = 25
    gemini_max_attempts: int = 1
    gemini_monthly_budget_microusd: int = MICROUSD_PER_USD
    gemini_input_microusd_per_million_tokens: int = 250_000
    gemini_output_microusd_per_million_tokens: int = 1_500_000
    gemini_pricing_configured: bool = False

    @classmethod
    def from_environment(cls) -> "BotSettings":
        groups = frozenset(
            value.strip() for value in os.environ.get("LINE_BOT_ALLOWED_GROUP_IDS", "").split(",")
            if value.strip()
        )
        vision_groups = frozenset(
            value.strip() for value in os.environ.get("LINE_BOT_VISION_PRODUCT_GROUP_IDS", "").split(",")
            if value.strip()
        )
        input_price = os.environ.get("GEMINI_INPUT_USD_PER_MILLION_TOKENS", "").strip()
        output_price = os.environ.get("GEMINI_OUTPUT_USD_PER_MILLION_TOKENS", "").strip()
        return cls(
            channel_secret=os.environ.get("LINE_BOT_CHANNEL_SECRET", ""),
            channel_access_token=os.environ.get("LINE_BOT_CHANNEL_ACCESS_TOKEN", ""),
            allowed_group_ids=groups,
            bot_user_id=os.environ.get("LINE_BOT_USER_ID", "").strip(),
            pos_base_url=os.environ.get("POS_LINE_BOT_BASE_URL", "").rstrip("/"),
            pos_shared_secret=os.environ.get("POS_LINE_BOT_SHARED_SECRET", ""),
            data_root=Path(os.environ.get("LINE_BOT_DATA_ROOT", "./line-bot-runtime")).expanduser().resolve(),
            port=int(os.environ.get("LINE_BOT_PORT", "8010")),
            retry_seconds=int(os.environ.get("LINE_BOT_RETRY_SECONDS", "300")),
            enrollment_mode=os.environ.get("LINE_BOT_ENROLLMENT_MODE", "0").strip().lower() in {"1", "true", "yes"},
            vision_product_group_ids=vision_groups,
            gemini_api_key=os.environ.get("GEMINI_API_KEY", ""),
            gemini_model=os.environ.get("GEMINI_MODEL", "").strip(),
            gemini_timeout_seconds=int(os.environ.get("GEMINI_TIMEOUT_SECONDS", "25")),
            gemini_max_attempts=int(os.environ.get("GEMINI_MAX_ATTEMPTS", "1")),
            gemini_monthly_budget_microusd=usd_to_microusd(
                os.environ.get("GEMINI_MONTHLY_BUDGET_USD", "1.00"), "GEMINI_MONTHLY_BUDGET_USD",
            ),
            gemini_input_microusd_per_million_tokens=(
                usd_to_microusd(input_price, "GEMINI_INPUT_USD_PER_MILLION_TOKENS") if input_price else 0
            ),
            gemini_output_microusd_per_million_tokens=(
                usd_to_microusd(output_price, "GEMINI_OUTPUT_USD_PER_MILLION_TOKENS") if output_price else 0
            ),
            gemini_pricing_configured=bool(input_price and output_price),
        )

    def validate(self) -> None:
        missing = []
        if len(self.channel_secret) < 16:
            missing.append("LINE_BOT_CHANNEL_SECRET")
        if len(self.channel_access_token) < 16:
            missing.append("LINE_BOT_CHANNEL_ACCESS_TOKEN")
        if not self.allowed_group_ids and not self.enrollment_mode:
            missing.append("LINE_BOT_ALLOWED_GROUP_IDS")
        if not self.pos_base_url.startswith("https://"):
            missing.append("POS_LINE_BOT_BASE_URL (https URL)")
        if len(self.pos_shared_secret) < 32:
            missing.append("POS_LINE_BOT_SHARED_SECRET")
        if not self.vision_product_group_ids.issubset(self.allowed_group_ids):
            missing.append("LINE_BOT_VISION_PRODUCT_GROUP_IDS (must be an allowed-group subset)")
        if self.vision_product_group_ids and not self.gemini_api_key:
            missing.append("GEMINI_API_KEY")
        if self.vision_product_group_ids and not self.gemini_model:
            missing.append("GEMINI_MODEL")
        if not 5 <= self.gemini_timeout_seconds <= 60:
            missing.append("GEMINI_TIMEOUT_SECONDS (5-60)")
        if self.gemini_max_attempts != 1:
            missing.append("GEMINI_MAX_ATTEMPTS (must be 1; no automatic Gemini retry)")
        if self.gemini_monthly_budget_microusd <= 0:
            missing.append("GEMINI_MONTHLY_BUDGET_USD")
        if self.vision_product_group_ids and not self.gemini_pricing_configured:
            missing.append("GEMINI_*_USD_PER_MILLION_TOKENS (explicit model pricing required)")
        if self.vision_product_group_ids and self.gemini_input_microusd_per_million_tokens <= 0:
            missing.append("GEMINI_INPUT_USD_PER_MILLION_TOKENS")
        if self.vision_product_group_ids and self.gemini_output_microusd_per_million_tokens <= 0:
            missing.append("GEMINI_OUTPUT_USD_PER_MILLION_TOKENS")
        if missing:
            raise RuntimeError("Missing or unsafe LINE Bot configuration: " + ", ".join(missing))
        self.data_root.mkdir(parents=True, exist_ok=True)
