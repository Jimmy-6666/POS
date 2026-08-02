"""Minimal HTTP clients for LINE Messaging API and signed POS integration."""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class PosUnavailable(RuntimeError):
    pass


class PosRejected(RuntimeError):
    def __init__(self, message: str, *, status_code: int = 0):
        super().__init__(message)
        self.status_code = status_code


class LineMessageRejected(RuntimeError):
    pass


LOG = logging.getLogger(__name__)


class LineMessagingClient:
    endpoint = "https://api.line.me/v2/bot/message"

    def __init__(self, access_token: str):
        self.access_token = access_token

    def _post(self, path: str, payload: dict) -> None:
        request = Request(
            self.endpoint + path,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urlopen(request, timeout=15):
                pass
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise LineMessageRejected(f"LINE Messaging API {exc.code}: {body[:1000]}") from exc

    def reply_text(self, reply_token: str, text: str) -> None:
        if reply_token:
            self._post("/reply", {"replyToken": reply_token, "messages": [{"type": "text", "text": text}]})

    def push_text(self, group_id: str, text: str, *, mention_user_id: str | None = None) -> None:
        message = {"type": "text", "text": text}
        if mention_user_id:
            mentioned_message = {
                "type": "textV2",
                "text": "{user}" + text,
                "substitution": {"user": {"type": "mention", "mentionee": {"userId": mention_user_id}}},
            }
            try:
                self._post("/push", {"to": group_id, "messages": [mentioned_message]})
                return
            except LineMessageRejected as exc:
                # A user may not be mentionable even when their webhook event
                # exposes a user ID. Delivering the business result is more
                # important than a best-effort mention.
                LOG.warning("LINE mention was rejected; sending plain group text instead: %s", exc)
        self._post("/push", {"to": group_id, "messages": [message]})

    @staticmethod
    def _buttons_message(text: str, labels: list[str]) -> dict:
        return {
            "type": "template",
            "altText": text,
            "template": {
                "type": "buttons",
                "text": text[:160],
                "actions": [
                    {"type": "message", "label": label[:20], "text": label}
                    for label in labels
                ],
            },
        }

    def push_buttons(self, group_id: str, text: str, labels: list[str]) -> None:
        self._post("/push", {
            "to": group_id,
            "messages": [self._buttons_message(text, labels)],
        })

    def reply_buttons(self, reply_token: str, text: str, labels: list[str]) -> None:
        if reply_token:
            self._post("/reply", {"replyToken": reply_token, "messages": [self._buttons_message(text, labels)]})

    def message_content(self, message_id: str) -> bytes:
        request = Request(
            f"https://api-data.line.me/v2/bot/message/{message_id}/content",
            headers={"Authorization": f"Bearer {self.access_token}"},
        )
        with urlopen(request, timeout=30) as response:
            return response.read()


class PosIntegrationClient:
    def __init__(self, base_url: str, shared_secret: str):
        self.base_url = base_url.rstrip("/")
        self.secret = shared_secret.encode("utf-8")

    def _signed_request(self, path: str, body: bytes, content_type: str, timeout: int):
        timestamp = str(int(time.time()))
        signature = hmac.new(self.secret, timestamp.encode("ascii") + b"." + body, hashlib.sha256).hexdigest()
        request = Request(
            self.base_url + path,
            data=body,
            method="POST",
            headers={
                "Content-Type": content_type,
                "X-POS-LineBot-Timestamp": timestamp,
                "X-POS-LineBot-Signature": signature,
            },
        )
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise PosRejected(body[:1000], status_code=exc.code) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise PosUnavailable(str(exc)) from exc

    def lookup(self, barcode: str) -> dict:
        body = json.dumps({"barcode": barcode}, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return self._signed_request("/_internal/line-bot/lookup", body, "application/json", 15)

    def apply(self, command: dict) -> dict:
        body = json.dumps(command, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        return self._signed_request("/_internal/line-bot/commands", body, "application/json", 30)
