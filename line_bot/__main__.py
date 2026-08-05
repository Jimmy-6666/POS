"""Command entry points for the VPS-resident LINE Bot."""

from __future__ import annotations

import argparse
import json

from .app import main as serve_main
from .config import BotSettings
from .storage import BotStore


def main() -> int:
    parser = argparse.ArgumentParser(prog="python -m line_bot")
    parser.add_argument(
        "command", nargs="?", choices=("gemini-budget",),
        help="Show secret-free Gemini monthly budget diagnostics.",
    )
    args = parser.parse_args()
    if args.command == "gemini-budget":
        settings = BotSettings.from_environment()
        settings.validate()
        store = BotStore(settings.data_root)
        print(json.dumps(
            store.gemini_budget_diagnostics(settings.gemini_monthly_budget_microusd),
            ensure_ascii=False,
            sort_keys=True,
        ))
        return 0
    return serve_main()


raise SystemExit(main())
