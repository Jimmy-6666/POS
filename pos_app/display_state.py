import json
import os
from datetime import datetime, timezone
from pathlib import Path


def signal_display(mode):
    """Notify the optional Windows launcher without affecting normal web operation."""
    state_file = os.environ.get("POS_DISPLAY_STATE_FILE")
    if not state_file or mode not in {"normal", "fullscreen"}:
        return
    path = Path(state_file)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(
        json.dumps({"mode": mode, "updated_at": datetime.now(timezone.utc).isoformat()}),
        encoding="utf-8",
    )
    temporary.replace(path)
