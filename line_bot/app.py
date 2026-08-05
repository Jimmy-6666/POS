"""Flask webhook application and in-process durable worker for the LINE Bot."""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import threading
import time

from flask import Flask, abort, jsonify, request

from .clients import LineMessagingClient, PosIntegrationClient
from .config import BotSettings
from .storage import BotStore
from .vision import GoogleProductVisionClient
from .workflow import BotWorkflow, ZxingBarcodeDecoder


LOG = logging.getLogger(__name__)


class BackgroundWorker(threading.Thread):
    SOURCE_IMAGE_CLEANUP_INTERVAL_SECONDS = 300

    def __init__(self, workflow: BotWorkflow, store: BotStore, *, bot_user_id: str, interval_seconds: float = 1.0):
        super().__init__(name="line-bot-worker", daemon=True)
        self.workflow = workflow
        self.store = store
        self.bot_user_id = bot_user_id
        self.interval_seconds = interval_seconds
        self.stop_event = threading.Event()
        self.next_source_image_cleanup_at = 0.0

    def stop(self) -> None:
        self.stop_event.set()

    def process_once(self) -> None:
        now = time.monotonic()
        if now >= self.next_source_image_cleanup_at:
            self.store.purge_expired_source_images()
            self.next_source_image_cleanup_at = now + self.SOURCE_IMAGE_CLEANUP_INTERVAL_SECONDS
        self.workflow.expire_flows()
        for item in self.store.claim_events():
            try:
                self.workflow.handle_event(item["event"], bot_user_id=self.bot_user_id)
            except Exception as exc:  # retain failure for support without stopping retry queue
                LOG.exception("LINE webhook event %s failed", item["event_key"])
                self.store.finish_event(item["event_key"], error=repr(exc))
            else:
                self.store.finish_event(item["event_key"])
        self.workflow.process_due_commands()
        self.workflow.process_due_notifications()

    def run(self) -> None:
        while not self.stop_event.is_set():
            self.process_once()
            self.stop_event.wait(self.interval_seconds)


class VisionWorker(threading.Thread):
    """Keep bounded Gemini work out of the webhook/legacy-flow worker."""

    CLEANUP_INTERVAL_SECONDS = 300

    def __init__(self, workflow: BotWorkflow, store: BotStore, *, interval_seconds: float = 1.0):
        super().__init__(name="line-bot-vision-worker", daemon=True)
        self.workflow = workflow
        self.store = store
        self.interval_seconds = interval_seconds
        self.stop_event = threading.Event()
        self.next_cleanup_at = 0.0

    def stop(self) -> None:
        self.stop_event.set()

    def process_once(self) -> None:
        now = time.monotonic()
        self.store.expire_vision_collections()
        if now >= self.next_cleanup_at:
            self.store.purge_expired_vision_jobs()
            self.next_cleanup_at = now + self.CLEANUP_INTERVAL_SECONDS
        self.workflow.process_due_vision_jobs(limit=1)

    def run(self) -> None:
        while not self.stop_event.is_set():
            self.process_once()
            self.stop_event.wait(self.interval_seconds)


def _valid_line_signature(channel_secret: str, raw: bytes, supplied: str) -> bool:
    expected = base64.b64encode(hmac.new(channel_secret.encode("utf-8"), raw, hashlib.sha256).digest()).decode("ascii")
    return bool(supplied) and hmac.compare_digest(expected, supplied)


def create_app(settings: BotSettings | None = None, *, line_client=None, pos_client=None,
               decoder=None, vision_client=None, start_worker: bool = True) -> Flask:
    settings = settings or BotSettings.from_environment()
    settings.validate()
    store = BotStore(settings.data_root)
    workflow = BotWorkflow(
        store,
        line_client or LineMessagingClient(settings.channel_access_token),
        pos_client or PosIntegrationClient(settings.pos_base_url, settings.pos_shared_secret),
        decoder or ZxingBarcodeDecoder(),
        retry_seconds=settings.retry_seconds,
        vision_client=vision_client or (
            GoogleProductVisionClient(
                settings.gemini_api_key,
                settings.gemini_model,
                timeout_seconds=settings.gemini_timeout_seconds,
            ) if settings.vision_product_group_ids else None
        ),
        vision_group_ids=settings.vision_product_group_ids,
        gemini_max_attempts=settings.gemini_max_attempts,
        gemini_monthly_budget_microusd=settings.gemini_monthly_budget_microusd,
        gemini_input_microusd_per_million_tokens=settings.gemini_input_microusd_per_million_tokens,
        gemini_output_microusd_per_million_tokens=settings.gemini_output_microusd_per_million_tokens,
    )
    app = Flask(__name__)
    app.config.update(BOT_SETTINGS=settings, BOT_STORE=store, BOT_WORKFLOW=workflow)
    worker = BackgroundWorker(workflow, store, bot_user_id=settings.bot_user_id)
    app.extensions["line_bot_worker"] = worker
    vision_worker = VisionWorker(workflow, store)
    app.extensions["line_bot_vision_worker"] = vision_worker

    @app.post("/webhook")
    def webhook():
        raw = request.get_data(cache=False)
        if not _valid_line_signature(settings.channel_secret, raw, request.headers.get("X-Line-Signature", "")):
            abort(401)
        try:
            payload = json.loads(raw)
        except (TypeError, ValueError, json.JSONDecodeError):
            abort(400)
        events = payload.get("events") if isinstance(payload, dict) else None
        if not isinstance(events, list):
            abort(400)
        accepted = 0
        for event in events:
            if not isinstance(event, dict):
                continue
            source = BotWorkflow.event_source(event)
            if not source:
                continue
            if settings.enrollment_mode:
                # A valid LINE signature is still required, but enrollment
                # must never process an existing legacy-group event.
                store.record_enrollment_group(source[0])
            elif source[0] in settings.allowed_group_ids and store.record_event(event):
                accepted += 1
        return jsonify(ok=True, accepted=accepted)

    @app.get("/health")
    def health():
        # No tokens, group IDs, or command contents are exposed by the liveness probe.
        with store.session() as db:
            db.execute("SELECT 1").fetchone()
        return jsonify(status="ok")

    if start_worker:
        worker.start()
        vision_worker.start()
    return app


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    app = create_app()
    from waitress import serve

    serve(app, host="127.0.0.1", port=app.config["BOT_SETTINGS"].port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
