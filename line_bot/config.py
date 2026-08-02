"""Explicit environment configuration for the VPS-resident LINE Bot."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


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

    @classmethod
    def from_environment(cls) -> "BotSettings":
        groups = frozenset(
            value.strip() for value in os.environ.get("LINE_BOT_ALLOWED_GROUP_IDS", "").split(",")
            if value.strip()
        )
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
        if missing:
            raise RuntimeError("Missing or unsafe LINE Bot configuration: " + ", ".join(missing))
        self.data_root.mkdir(parents=True, exist_ok=True)
        (self.data_root / "images").mkdir(parents=True, exist_ok=True)
