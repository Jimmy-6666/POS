"""LINE group conversation state machine and durable POS retry worker."""

from __future__ import annotations

import secrets
import threading
import logging
import re
from io import BytesIO
from typing import Any, Protocol

from .clients import LineMessageRejected, PosRejected, PosUnavailable
from .config import MICROUSD_PER_USD
from .vision import (
    MAX_GEMINI_INPUT_TOKENS,
    MAX_GEMINI_RESPONSE_TOKENS,
    MAX_VISION_IMAGE_DIMENSION,
    MAX_VISION_IMAGE_PIXELS,
    GeminiUsage,
    ProductVisionClient,
    ProductVisionResult,
    VisionError,
    VisionInputError,
    VisionRetryableError,
    normalize_product_name,
)


LOG = logging.getLogger(__name__)
MONTHLY_LIMIT_NOTIFICATION_RETRY_SECONDS = 60 * 60


class BarcodeDecoder(Protocol):
    def decode(self, image_bytes: bytes) -> str | None: ...

    def decode_all(self, image_bytes: bytes) -> set[str]: ...


class ZxingBarcodeDecoder:
    """Decode linear retail barcodes, but never QR or other matrix codes."""

    def decode(self, image_bytes: bytes) -> str | None:
        results = self.decode_all(image_bytes)
        return next(iter(results), None)

    def decode_all(self, image_bytes: bytes) -> set[str]:
        try:
            import zxingcpp
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("Barcode decoder dependencies are not installed.") from exc
        with Image.open(BytesIO(image_bytes)) as image:
            results = zxingcpp.read_barcodes(
                image,
                formats=zxingcpp.BarcodeFormat.LinearCodes,
            )
        return {str(item.text).strip() for item in results if str(item.text).strip()}


def _whole_baht(value: str, *, positive: bool = False) -> int | None:
    value = str(value or "").strip()
    if not value.isdigit() or (len(value) > 1 and value.startswith("0")):
        return None
    amount = int(value)
    if amount > 999_999_999 or (positive and amount <= 0):
        return None
    return amount


_COST_BAHT_RE = re.compile(r"^(?:0|[1-9][0-9]{0,8})(?:\.[0-9]{1,2})?$")


def _cost_satang(value: str) -> int | None:
    """Parse a user-entered baht amount exactly, allowing up to two satang digits."""

    text = str(value or "").strip()
    if not _COST_BAHT_RE.fullmatch(text):
        return None
    whole, separator, fractional = text.partition(".")
    satang = int(whole) * 100
    if separator:
        satang += int(fractional.ljust(2, "0"))
    return satang


def _format_satang(value: int) -> str:
    whole, fractional = divmod(int(value), 100)
    return f"{whole}.{fractional:02d}"


def _flow_data_product(product: dict[str, Any]) -> dict[str, Any]:
    raw_cost = product.get("cost_satang")
    if isinstance(raw_cost, bool) or not str(raw_cost if raw_cost is not None else "").isdigit():
        raw_cost = _cost_satang(product.get("cost_baht"))
    if raw_cost is None:
        raise ValueError("POS product response has no valid cost amount.")
    return {
        "product_uuid": product["product_uuid"],
        "revision": product["revision"],
        "name_th": product["name_th"],
        "cost_satang": int(raw_cost),
        "sale_baht": product["sale_baht"],
        "is_placeholder": product["is_placeholder"],
    }


class BotWorkflow:
    MESSAGE_ACTIONS = {
        "EXISTING_CHOICE": {"แก้ราคาทุน/ราคาขาย": "prices"},
        "OFFER_CREATE": {"เพิ่มสินค้า": "add", "ยกเลิก": "cancel"},
        "REVIEW_PRICE": {"ยืนยัน": "confirm", "แก้ไข": "edit", "ยกเลิก": "cancel"},
        "REVIEW_CREATE": {"ยืนยัน": "confirm", "แก้ไข": "edit", "ยกเลิก": "cancel"},
        "VISION_EXISTING_SALE_REVIEW": {"แก้ราคาขาย": "sale", "ยกเลิก": "cancel"},
        "VISION_EXISTING_FINAL_REVIEW": {"ยืนยัน": "confirm", "แก้ราคา": "edit_price", "ยกเลิก": "cancel"},
        "VISION_NAME_REVIEW": {"ใช้ชื่อนี้": "use_name", "แก้ไขชื่อ": "edit_name", "ยกเลิก": "cancel"},
        "VISION_FINAL_REVIEW": {"ยืนยัน": "confirm", "แก้ชื่อ": "edit_name", "แก้ราคา": "edit_price", "ยกเลิก": "cancel"},
    }

    def __init__(
        self,
        store,
        line_client,
        pos_client,
        decoder: BarcodeDecoder,
        *,
        retry_seconds: int = 300,
        barcode_timeout_seconds: float = 10.0,
        vision_client: ProductVisionClient | None = None,
        vision_group_ids: frozenset[str] = frozenset(),
        gemini_max_attempts: int = 1,
        gemini_monthly_budget_microusd: int = MICROUSD_PER_USD,
        gemini_input_microusd_per_million_tokens: int = 250_000,
        gemini_output_microusd_per_million_tokens: int = 1_500_000,
    ):
        self.store = store
        self.line = line_client
        self.pos = pos_client
        self.decoder = decoder
        self.retry_seconds = retry_seconds
        self.barcode_timeout_seconds = barcode_timeout_seconds
        self.vision_client = vision_client
        self.vision_group_ids = vision_group_ids
        self.gemini_max_attempts = gemini_max_attempts
        self.gemini_monthly_budget_microusd = gemini_monthly_budget_microusd
        self.gemini_input_microusd_per_million_tokens = gemini_input_microusd_per_million_tokens
        self.gemini_output_microusd_per_million_tokens = gemini_output_microusd_per_million_tokens

    @staticmethod
    def _token_cost_microusd(tokens: int, microusd_per_million_tokens: int) -> int:
        """Round a token price upward so a reservation cannot undercount cost."""

        return (int(tokens) * int(microusd_per_million_tokens) + 999_999) // 1_000_000

    def _reserved_gemini_cost_microusd(self) -> int:
        return (
            self._token_cost_microusd(MAX_GEMINI_INPUT_TOKENS, self.gemini_input_microusd_per_million_tokens)
            + self._token_cost_microusd(MAX_GEMINI_RESPONSE_TOKENS, self.gemini_output_microusd_per_million_tokens)
        )

    def _settle_gemini_usage(self, request_key: str, usage: GeminiUsage | None) -> None:
        if usage is None:
            # Unknown usage is intentionally charged at the full reservation.
            # This is stricter than trusting a failed/partial response to be free.
            self.store.retain_gemini_reservation(request_key)
            return
        actual_cost = (
            self._token_cost_microusd(usage.prompt_tokens, self.gemini_input_microusd_per_million_tokens)
            + self._token_cost_microusd(
                usage.candidate_tokens + usage.thought_tokens,
                self.gemini_output_microusd_per_million_tokens,
            )
        )
        self.store.settle_gemini_request(
            request_key,
            actual_cost_microusd=actual_cost,
            input_tokens=usage.prompt_tokens,
            output_tokens=usage.candidate_tokens,
            thought_tokens=usage.thought_tokens,
        )

    @staticmethod
    def event_source(event: dict[str, Any]) -> tuple[str, str] | None:
        source = event.get("source") if isinstance(event.get("source"), dict) else {}
        if source.get("type") != "group":
            return None
        group_id = str(source.get("groupId") or "")
        user_id = str(source.get("userId") or "")
        return (group_id, user_id) if group_id and user_id else None

    def _buttons(
        self,
        group_id: str,
        text: str,
        actions: list[tuple[str, str]],
        *,
        reply_token: str = "",
    ) -> None:
        # LINE group postback events don't reliably include the actor user ID.
        # Message actions show the chosen label in the chat and retain the
        # actor's user ID in the resulting message webhook.
        labels = [label for label, _ in actions]
        if reply_token:
            try:
                self.line.reply_buttons(reply_token, text, labels)
                return
            except Exception:
                # The quoted-message result is still useful if LINE rejects an
                # expired reply token, so send it as a group push instead.
                pass
        self.line.push_buttons(group_id, text, labels)

    def _save_flow(self, group_id: str, user_id: str, conversation: dict, state: str, data: dict) -> None:
        self.store.update_flow(group_id, user_id, state=state, data=data)

    def _reply_or_push_text(self, reply_token: str, group_id: str, text: str) -> None:
        if reply_token:
            try:
                self.line.reply_text(reply_token, text)
                return
            except Exception:
                # A delayed worker can no longer use the one-time reply token.
                pass
        self.line.push_text(group_id, text)

    def _decode_barcode_with_timeout(self, message_id: str) -> str | None:
        result: list[str | None] = [None]
        completed = threading.Event()

        def decode() -> None:
            try:
                decoded = self.decoder.decode(self.line.message_content(message_id))
                result[0] = str(decoded).strip() if decoded else None
            except Exception:
                result[0] = None
            finally:
                completed.set()

        threading.Thread(target=decode, name="line-barcode-decode", daemon=True).start()
        return result[0] if completed.wait(self.barcode_timeout_seconds) else None

    def is_trigger(self, message: dict, *, bot_user_id: str) -> bool:
        text = str(message.get("text") or "").strip()
        if text == "บอท":
            return True
        mention = message.get("mention") if isinstance(message.get("mention"), dict) else {}
        for item in mention.get("mentionees", []) if isinstance(mention.get("mentionees"), list) else []:
            if item.get("type") == "user" and bot_user_id and item.get("userId") == bot_user_id:
                return True
        return False

    def handle_event(self, event: dict[str, Any], *, bot_user_id: str = "") -> None:
        source = self.event_source(event)
        if not source:
            return
        group_id, user_id = source
        event_type = event.get("type")
        if event_type != "message":
            return
        message = event.get("message") if isinstance(event.get("message"), dict) else {}
        if message.get("type") == "image":
            message_id = str(message.get("id") or "")
            if group_id in self.vision_group_ids:
                self.handle_vision_image(event, group_id, user_id, message_id)
            elif message_id:
                self.store.remember_source_image(message_id, group_id, user_id)
            return
        if message.get("type") != "text":
            return
        quote_id = str(message.get("quotedMessageId") or "")
        if quote_id and self.is_trigger(message, bot_user_id=bot_user_id):
            self.start_quoted_image(event, group_id, user_id, quote_id)
            return
        self.handle_text_input(
            group_id,
            user_id,
            str(message.get("text") or ""),
            reply_token=str(event.get("replyToken") or ""),
        )

    def handle_vision_image(self, event: dict[str, Any], group_id: str, user_id: str, message_id: str) -> None:
        """Collect two Vision images durably; webhook processing remains quick."""

        if not message_id or self.store.conversation(group_id, user_id):
            return
        message = event.get("message") if isinstance(event.get("message"), dict) else {}
        image_set = message.get("imageSet") if isinstance(message.get("imageSet"), dict) else None
        reply_token = str(event.get("replyToken") or "")
        image_set_id = None
        image_index = None
        if image_set is not None:
            try:
                image_set_id = str(image_set.get("id") or "")
                image_index = int(image_set.get("index"))
                total = int(image_set.get("total"))
            except (TypeError, ValueError):
                total = 0
            if not image_set_id or total != 2 or image_index not in {1, 2}:
                self._reply_or_push_text(
                    reply_token,
                    group_id,
                    "กรุณาส่งรูปด้านหน้าและด้านหลังพร้อมกันครั้งละ 2 รูปครับ 😊",
                )
                return
        result = self.store.record_vision_image(
            group_id,
            user_id,
            message_id,
            image_set_id=image_set_id,
            image_index=image_index,
            reply_token=reply_token,
        )
        if result["status"] == "invalid":
            self._reply_or_push_text(
                reply_token,
                group_id,
                "กรุณาส่งรูปด้านหน้าและด้านหลังพร้อมกันครั้งละ 2 รูปครับ 😊",
            )

    @staticmethod
    def _validate_vision_image(image_bytes: bytes) -> None:
        """Reject malformed or decompression-bomb images before barcode/Gemini work."""

        try:
            from PIL import Image

            with Image.open(BytesIO(image_bytes)) as inspected:
                inspected.verify()
            with Image.open(BytesIO(image_bytes)) as image:
                if image.width > MAX_VISION_IMAGE_DIMENSION or image.height > MAX_VISION_IMAGE_DIMENSION:
                    raise VisionInputError("Image dimensions exceeded the limit.")
                if image.width * image.height > MAX_VISION_IMAGE_PIXELS:
                    raise VisionInputError("Image pixel count exceeded the limit.")
                image.load()
        except VisionInputError:
            raise
        except Exception as exc:
            raise VisionInputError("Image content was not readable.") from exc

    def _decode_all_barcodes(self, image_bytes: bytes) -> set[str]:
        decoder_all = getattr(self.decoder, "decode_all", None)
        if callable(decoder_all):
            return {str(code).strip() for code in decoder_all(image_bytes) if str(code).strip()}
        barcode = self.decoder.decode(image_bytes)
        return {str(barcode).strip()} if barcode else set()

    def _download_vision_images(self, image_message_ids: dict[str, str]) -> list[bytes]:
        ids = [str(image_message_ids.get(str(index)) or "") for index in (1, 2)]
        if not all(ids):
            raise VisionInputError("Vision job did not contain two message IDs.")
        images = [self.line.message_content(message_id) for message_id in ids]
        for image in images:
            self._validate_vision_image(image)
        return images

    def _start_vision_manual_name(self, job: dict[str, Any], barcode: str, product: dict[str, Any] | None) -> None:
        data: dict[str, Any] = {"barcode": barcode}
        if product:
            data["product"] = product
        self.store.start_flow(job["group_id"], job["user_id"], secrets.token_urlsafe(12), "VISION_NAME_EDIT", data)
        self._reply_or_push_text(
            job.get("reply_token", ""),
            job["group_id"],
            "ผมอ่านชื่อสินค้าอัตโนมัติไม่สำเร็จครับ\nกรุณาพิมพ์ชื่อสินค้าที่ถูกต้องได้เลยครับ 😊",
        )

    def _start_vision_budget_manual_name(
        self, job: dict[str, Any], barcode: str, product: dict[str, Any] | None
    ) -> None:
        """Continue the normal manual workflow without consuming provider quota."""

        data: dict[str, Any] = {"barcode": barcode}
        if product:
            data["product"] = product
        self.store.start_flow(job["group_id"], job["user_id"], secrets.token_urlsafe(12), "VISION_NAME_EDIT", data)
        self._reply_or_push_text(
            job.get("reply_token", ""),
            job["group_id"],
            "วงเงิน AI สำหรับเดือนนี้ครบแล้วครับ\nกรุณาพิมพ์ชื่อสินค้าเองได้เลย 😊",
        )

    def _start_vision_existing_sale(self, job: dict[str, Any], barcode: str, product: dict[str, Any]) -> None:
        data = {"barcode": barcode, "product": product}
        self.store.start_flow(job["group_id"], job["user_id"], secrets.token_urlsafe(12), "VISION_EXISTING_SALE_REVIEW", data)
        self._buttons(
            job["group_id"],
            f"พบสินค้าในระบบแล้วครับ 😊\nชื่อสินค้า : {product['name_th']}\nบาร์โค้ด : {barcode}\nราคาขาย : {product['sale_baht']} บาท\nต้องการแก้ราคาขายหรือไม่ครับ",
            [("แก้ราคาขาย", "sale"), ("ยกเลิก", "cancel")],
            reply_token=job.get("reply_token", ""),
        )

    def _start_vision_name_review(
        self,
        job: dict[str, Any],
        barcode: str,
        product: dict[str, Any] | None,
        result: ProductVisionResult,
    ) -> None:
        data: dict[str, Any] = {"barcode": barcode, "suggested_name_th": result.suggested_name_th}
        if product:
            data["product"] = product
        self.store.start_flow(job["group_id"], job["user_id"], secrets.token_urlsafe(12), "VISION_NAME_REVIEW", data)
        self._buttons(
            job["group_id"],
            f"พบสินค้าใหม่ครับ 😊\nบาร์โค้ด : {barcode}\nชื่อที่ระบบเสนอ :\n{result.suggested_name_th}\n\nกรุณาตรวจสอบชื่อสินค้าครับ",
            [("ใช้ชื่อนี้", "use_name"), ("แก้ไขชื่อ", "edit_name"), ("ยกเลิก", "cancel")],
            reply_token=job.get("reply_token", ""),
        )

    def process_due_vision_jobs(self, limit: int = 1) -> None:
        """Run at most one Gemini job in the dedicated Vision worker."""

        for job in self.store.claim_due_vision_jobs(limit):
            images: list[bytes] = []
            barcode: str | None = None
            product: dict[str, Any] | None = None
            gemini_request_key = ""
            try:
                images = self._download_vision_images(job["image_message_ids"])
                barcodes: set[str] = set()
                for image in images:
                    barcodes.update(self._decode_all_barcodes(image))
                if not barcodes:
                    self.store.fail_vision_job(job["job_id"], "No barcode decoded from Vision images.")
                    self._reply_or_push_text(
                        job.get("reply_token", ""), job["group_id"],
                        "ผมอ่านบาร์โค้ดจากรูปไม่สำเร็จครับ กรุณาส่งรูปด้านหลังที่ชัดเจนอีกครั้งครับ 😊",
                    )
                    continue
                if len(barcodes) != 1:
                    self.store.fail_vision_job(job["job_id"], "Multiple distinct barcodes decoded from Vision images.")
                    self._reply_or_push_text(
                        job.get("reply_token", ""), job["group_id"],
                        "ผมพบบาร์โค้ดมากกว่าหนึ่งรายการครับ กรุณาส่งรูปสินค้าใหม่อีกครั้งครับ 😊",
                    )
                    continue
                barcode = next(iter(barcodes))
                try:
                    lookup = self.pos.lookup(barcode)
                except PosUnavailable:
                    if self.store.retry_vision_job(
                        job["job_id"], "POS lookup was unavailable.",
                        retry_seconds=self.retry_seconds, max_attempts=self.gemini_max_attempts,
                    ):
                        continue
                    self._reply_or_push_text(
                        job.get("reply_token", ""), job["group_id"],
                        "ผมยังเชื่อมต่อกับร้านไม่ได้ครับ กรุณาลองส่งรูปใหม่อีกครั้งภายหลังครับ 😥",
                    )
                    continue
                except PosRejected:
                    self.store.fail_vision_job(job["job_id"], "POS lookup was rejected.")
                    self._reply_or_push_text(
                        job.get("reply_token", ""), job["group_id"],
                        "ผมไม่สามารถตรวจสอบข้อมูลสินค้าจากร้านได้ครับ 😥",
                    )
                    continue
                raw_product = lookup.get("product")
                product = _flow_data_product(raw_product) if raw_product else None
                if product and not product["is_placeholder"]:
                    self._start_vision_existing_sale(job, barcode, product)
                    self.store.complete_vision_job(job["job_id"])
                    continue
                if not self.vision_client:
                    self.store.fail_vision_job(job["job_id"], "Vision client was unavailable for a Vision group.")
                    self._start_vision_manual_name(job, barcode, product)
                    continue
                reservation = self.store.reserve_gemini_request(
                    job_id=job["job_id"],
                    attempt=int(job["attempts"]),
                    budget_microusd=self.gemini_monthly_budget_microusd,
                    reserved_cost_microusd=self._reserved_gemini_cost_microusd(),
                )
                if not reservation["allowed"]:
                    reason = reservation["reason"]
                    self.store.fail_vision_job(
                        job["job_id"],
                        "Gemini request was not invoked: " + reason + ".",
                    )
                    self._start_vision_budget_manual_name(job, barcode, product)
                    continue
                gemini_request_key = str(reservation["request_key"])
                if not self.store.start_gemini_request(gemini_request_key):
                    self.store.fail_vision_job(job["job_id"], "Gemini request was already claimed.")
                    self._start_vision_budget_manual_name(job, barcode, product)
                    continue
                try:
                    result = self.vision_client.analyze_product(images)
                except VisionRetryableError as exc:
                    self._settle_gemini_usage(gemini_request_key, exc.usage)
                    if self.store.retry_vision_job(
                        job["job_id"], "Gemini was temporarily unavailable.",
                        retry_seconds=1, max_attempts=self.gemini_max_attempts,
                    ):
                        continue
                    self._start_vision_manual_name(job, barcode, product)
                    continue
                except VisionError as exc:
                    self._settle_gemini_usage(gemini_request_key, exc.usage)
                    self._start_vision_manual_name(job, barcode, product)
                    self.store.complete_vision_job(job["job_id"])
                    continue
                self._settle_gemini_usage(gemini_request_key, result.usage)
                if not result.same_product:
                    self.store.fail_vision_job(job["job_id"], "Gemini identified distinct products.")
                    self._reply_or_push_text(
                        job.get("reply_token", ""), job["group_id"],
                        "รูปทั้งสองดูเป็นคนละสินค้าครับ กรุณาส่งรูปสินค้าใหม่อีกครั้งครับ 😊",
                    )
                    continue
                if not result.suggested_name_th:
                    self._start_vision_manual_name(job, barcode, product)
                    self.store.complete_vision_job(job["job_id"])
                    continue
                self._start_vision_name_review(job, barcode, product, result)
                self.store.complete_vision_job(job["job_id"])
            except Exception:
                LOG.error("Vision product job failed without exposing image or secret data")
                if gemini_request_key:
                    self.store.retain_gemini_reservation(gemini_request_key)
                self.store.fail_vision_job(job["job_id"], "Vision job processing failed.")
                if barcode:
                    self._start_vision_manual_name(job, barcode, product)
                else:
                    self._reply_or_push_text(
                        job.get("reply_token", ""), job["group_id"],
                        "ผมอ่านบาร์โค้ดจากรูปไม่สำเร็จครับ กรุณาส่งรูปด้านหลังที่ชัดเจนอีกครั้งครับ 😊",
                    )
            finally:
                images.clear()

    def start_quoted_image(self, event: dict, group_id: str, user_id: str, quote_id: str) -> None:
        original = self.store.source_image(quote_id)
        if not original or original["group_id"] != group_id:
            self.line.push_text(group_id, "กรุณา Quote รูปบาร์โค้ดในกลุ่มนี้ภายใน 24 ชั่วโมง แล้วเรียกบอทอีกครั้งครับ 😊")
            return
        reply_token = str(event.get("replyToken") or "")
        active_flow = self.store.group_conversation(group_id)
        if active_flow and not active_flow["state"].startswith("VISION_"):
            self._reply_or_push_text(
                reply_token,
                group_id,
                "มีรายการแก้ไขสินค้าในกลุ่มกำลังดำเนินการอยู่ครับ กรุณายืนยันหรือยกเลิกก่อนเริ่มรายการใหม่ 😊",
            )
            return
        barcode = self._decode_barcode_with_timeout(quote_id)
        if not barcode:
            self._reply_or_push_text(
                reply_token,
                group_id,
                "ผมอ่านบาร์โค้ดจากรูปไม่สำเร็จภายใน 10 วินาทีครับ กรุณาส่งรูปบาร์โค้ดที่ชัดเจนแล้วลองใหม่อีกครั้งครับ 😥",
            )
            return
        try:
            result = self.pos.lookup(barcode)
        except PosUnavailable:
            self._reply_or_push_text(reply_token, group_id, "ผมยังเชื่อมต่อกับร้านไม่ได้ครับ ลองเรียกผมใหม่อีกครั้งภายหลังครับ 😥")
            return
        except PosRejected:
            self._reply_or_push_text(reply_token, group_id, "ผมไม่สามารถตรวจสอบข้อมูลสินค้าจากร้านได้ครับ 😥")
            return
        product = result.get("product")
        flow_id = secrets.token_urlsafe(12)
        data = {"barcode": barcode, "source_image_id": quote_id}
        normalized_product = None
        if product:
            try:
                normalized_product = _flow_data_product(product)
            except (KeyError, TypeError, ValueError):
                LOG.exception("POS returned an invalid product summary for LINE Bot lookup")
                self._reply_or_push_text(
                    reply_token,
                    group_id,
                    "ผมไม่สามารถตรวจสอบข้อมูลสินค้าจากร้านได้ครับ กรุณาลองใหม่อีกครั้งครับ 😥",
                )
                return
        if product and not product.get("is_placeholder"):
            data["product"] = normalized_product
            self.store.start_flow(group_id, user_id, flow_id, "EXISTING_CHOICE", data)
            self._buttons(
                group_id,
                f"พบสินค้าในระบบแล้วครับ 😊\nชื่อสินค้า : {product['name_th']}\nราคาทุน : {_format_satang(normalized_product['cost_satang'])} บาท\nราคาขาย : {product['sale_baht']} บาท\nต้องการทำรายการใดครับ",
                [("แก้ราคาทุน/ราคาขาย", "prices")],
                reply_token=reply_token,
            )
            return
        if product:
            data["product"] = normalized_product
        self.store.start_flow(group_id, user_id, flow_id, "OFFER_CREATE", data)
        self._buttons(
            group_id,
            f"ผมสามารถอ่าน บาร์โค้ด : {barcode} ได้ครับ 😊 แต่ไม่พบชื่อสินค้าชิ้นนี้ครับ ต้องการเพิ่มสินค้าชิ้นนี้ไหมครับ",
            [("เพิ่มสินค้า", "add"), ("ยกเลิก", "cancel")],
            reply_token=reply_token,
        )

    def handle_flow_action(
        self,
        group_id: str,
        user_id: str,
        conversation: dict,
        action: str,
        *,
        reply_token: str = "",
        actor_user_id: str | None = None,
    ) -> None:
        state = conversation["state"]
        data = conversation["data"]
        if action == "cancel":
            self.store.close_flow(group_id, user_id)
            self._reply_or_push_text(reply_token, group_id, "ผมยกเลิกรายการเปลี่ยนแปลงแล้วครับ 🌷")
            return
        if state == "EXISTING_CHOICE" and action == "prices":
            self._save_flow(group_id, user_id, conversation, "PRICE_COST", data)
            self._reply_or_push_text(reply_token, group_id, "แก้ราคาทุนเป็นเท่าไหร่ดีครับ\n(หากไม่ทราบระบุ 0) 😊")
        elif state == "OFFER_CREATE" and action == "add":
            self._save_flow(group_id, user_id, conversation, "CREATE_NAME", data)
            self._reply_or_push_text(reply_token, group_id, "สินค้านี้ชื่ออะไรครับ 😊")
        elif state == "VISION_EXISTING_SALE_REVIEW" and action == "sale":
            self._save_flow(group_id, user_id, conversation, "VISION_EXISTING_WAIT_SALE_PRICE", data)
            self._reply_or_push_text(reply_token, group_id, "สินค้านี้ราคาขายเท่าไหร่ครับ 😊")
        elif state == "VISION_NAME_REVIEW" and action == "use_name":
            data["name_th"] = data["suggested_name_th"]
            self._save_flow(group_id, user_id, conversation, "VISION_WAIT_SALE_PRICE", data)
            self._reply_or_push_text(reply_token, group_id, "สินค้านี้ราคาขายเท่าไหร่ครับ 😊")
        elif state in {"VISION_NAME_REVIEW", "VISION_FINAL_REVIEW"} and action == "edit_name":
            self._save_flow(group_id, user_id, conversation, "VISION_NAME_EDIT", data)
            self._reply_or_push_text(reply_token, group_id, "กรุณาพิมพ์ชื่อสินค้าที่ถูกต้องครับ 😊")
        elif state in {"REVIEW_PRICE", "REVIEW_CREATE", "VISION_EXISTING_FINAL_REVIEW", "VISION_FINAL_REVIEW"} and action == "confirm":
            self.confirm_flow(
                group_id,
                user_id,
                conversation,
                reply_token=reply_token,
                actor_user_id=actor_user_id,
            )
        elif state == "REVIEW_PRICE" and action == "edit":
            data.pop("cost_satang", None)
            data.pop("sale_baht", None)
            self._save_flow(group_id, user_id, conversation, "PRICE_COST", data)
            self._reply_or_push_text(reply_token, group_id, "แก้ราคาทุนเป็นเท่าไหร่ดีครับ\n(หากไม่ทราบระบุ 0) 😊")
        elif state == "REVIEW_CREATE" and action == "edit":
            self._save_flow(group_id, user_id, conversation, "CREATE_NAME", data)
            self._reply_or_push_text(reply_token, group_id, "สินค้านี้ชื่ออะไรครับ 😊")
        elif state == "VISION_EXISTING_FINAL_REVIEW" and action == "edit_price":
            data.pop("sale_baht", None)
            self._save_flow(group_id, user_id, conversation, "VISION_EXISTING_WAIT_SALE_PRICE", data)
            self._reply_or_push_text(reply_token, group_id, "สินค้านี้ราคาขายเท่าไหร่ครับ 😊")
        elif state == "VISION_FINAL_REVIEW" and action == "edit_price":
            data.pop("sale_baht", None)
            self._save_flow(group_id, user_id, conversation, "VISION_WAIT_SALE_PRICE", data)
            self._reply_or_push_text(reply_token, group_id, "สินค้านี้ราคาขายเท่าไหร่ครับ 😊")

    def handle_text_input(self, group_id: str, user_id: str, text: str, *, reply_token: str = "") -> None:
        actor_user_id = user_id
        conversation = self.store.conversation(group_id, user_id)
        if not conversation:
            shared_flow = self.store.group_conversation(group_id)
            if not shared_flow or shared_flow["state"].startswith("VISION_"):
                return
            user_id = shared_flow["user_id"]
            conversation = shared_flow
        state, data = conversation["state"], conversation["data"]
        action = self.MESSAGE_ACTIONS.get(state, {}).get(text.strip())
        if action:
            self.handle_flow_action(
                group_id,
                user_id,
                conversation,
                action,
                reply_token=reply_token,
                actor_user_id=actor_user_id,
            )
            return
        if state == "VISION_EXISTING_WAIT_SALE_PRICE":
            sale = _whole_baht(text, positive=True)
            if sale is None:
                self._save_flow(group_id, user_id, conversation, state, data)
                self._reply_or_push_text(reply_token, group_id, "กรุณาระบุราคาขายให้เกิน 0 บาท 😊")
                return
            data["sale_baht"] = sale
            self._review_vision_existing(group_id, user_id, conversation, data, reply_token=reply_token)
        elif state == "VISION_NAME_EDIT":
            name = normalize_product_name(text)
            if not name or len(name) > 160 or name.startswith("สินค้าไม่ทราบชื่อ ("):
                self._save_flow(group_id, user_id, conversation, state, data)
                self._reply_or_push_text(reply_token, group_id, "กรุณาระบุชื่อสินค้าที่ถูกต้อง ไม่เกิน 160 ตัวอักษรครับ 😊")
                return
            data["name_th"] = name
            self._save_flow(group_id, user_id, conversation, "VISION_WAIT_SALE_PRICE", data)
            self._reply_or_push_text(reply_token, group_id, "สินค้านี้ราคาขายเท่าไหร่ครับ 😊")
        elif state == "VISION_WAIT_SALE_PRICE":
            sale = _whole_baht(text, positive=True)
            if sale is None:
                self._save_flow(group_id, user_id, conversation, state, data)
                self._reply_or_push_text(reply_token, group_id, "กรุณาระบุราคาขายให้เกิน 0 บาท 😊")
                return
            data["sale_baht"] = sale
            self._review_vision_create(group_id, user_id, conversation, data, reply_token=reply_token)
        elif state == "PRICE_COST":
            cost = _cost_satang(text)
            if cost is None:
                self._save_flow(group_id, user_id, conversation, state, data)
                self._reply_or_push_text(reply_token, group_id, "กรุณาระบุราคาทุนเป็นจำนวนบาทและสตางค์ไม่เกิน 2 ตำแหน่งครับ 😊")
                return
            data["cost_satang"] = cost
            self._save_flow(group_id, user_id, conversation, "PRICE_SALE", data)
            self._reply_or_push_text(reply_token, group_id, "แก้ราคาขายเป็นเท่าไหร่ดีครับ 😊")
        elif state == "PRICE_SALE":
            sale = _whole_baht(text, positive=True)
            if sale is None:
                self._save_flow(group_id, user_id, conversation, state, data)
                self._reply_or_push_text(reply_token, group_id, "กรุณาระบุราคาขายให้เกิน 0 บาท 😊")
                return
            if data.get("cost_satang", 0) and sale * 100 <= data["cost_satang"]:
                self._save_flow(group_id, user_id, conversation, state, data)
                self._reply_or_push_text(
                    reply_token, group_id,
                    f"กรุณาระบุราคาขาย ที่มากกว่าราคาทุน {_format_satang(data['cost_satang'])} บาท 😊",
                )
                return
            data["sale_baht"] = sale
            self._review_price(group_id, user_id, conversation, data, reply_token=reply_token)
        elif state == "CREATE_NAME":
            name = text.strip()
            if not name or len(name) > 160 or name.startswith("สินค้าไม่ทราบชื่อ ("):
                self._save_flow(group_id, user_id, conversation, state, data)
                self._reply_or_push_text(reply_token, group_id, "กรุณาระบุชื่อสินค้าที่ถูกต้อง ไม่เกิน 160 ตัวอักษรครับ 😊")
                return
            data["name_th"] = name
            self._save_flow(group_id, user_id, conversation, "CREATE_COST", data)
            self._reply_or_push_text(reply_token, group_id, "สินค้านี้ต้นทุนเท่าไหร่ครับ\n(หากไม่ทราบระบุ 0) 😊")
        elif state == "CREATE_COST":
            cost = _cost_satang(text)
            if cost is None:
                self._save_flow(group_id, user_id, conversation, state, data)
                self._reply_or_push_text(reply_token, group_id, "กรุณาระบุต้นทุนเป็นจำนวนบาทและสตางค์ไม่เกิน 2 ตำแหน่งครับ 😊")
                return
            data["cost_satang"] = cost
            self._save_flow(group_id, user_id, conversation, "CREATE_SALE", data)
            self._reply_or_push_text(reply_token, group_id, "สินค้านี้ราคาขายเท่าไหร่ครับ 😊")
        elif state == "CREATE_SALE":
            sale = _whole_baht(text, positive=True)
            if sale is None:
                self._save_flow(group_id, user_id, conversation, state, data)
                self._reply_or_push_text(reply_token, group_id, "กรุณาระบุราคาขายให้เกิน 0 บาท 😊")
                return
            if data.get("cost_satang", 0) and sale * 100 <= data["cost_satang"]:
                self._save_flow(group_id, user_id, conversation, state, data)
                self._reply_or_push_text(
                    reply_token, group_id,
                    f"กรุณาระบุราคาขาย ที่มากกว่าราคาทุน {_format_satang(data['cost_satang'])} บาท 😊",
                )
                return
            data["sale_baht"] = sale
            self._review_create(group_id, user_id, conversation, data, reply_token=reply_token)

    def _review_price(
        self, group_id: str, user_id: str, conversation: dict, data: dict, *, reply_token: str = ""
    ) -> None:
        self._save_flow(group_id, user_id, conversation, "REVIEW_PRICE", data)
        product = data["product"]
        self._buttons(
            group_id,
            f"ชื่อสินค้า : {product['name_th']}\nราคาทุน : {_format_satang(data['cost_satang'])} บาท\nราคาขาย : {data['sale_baht']} บาท\nรบกวนยืนยันรายละเอียดให้ผมด้วยครับ 😊",
            [("ยืนยัน", "confirm"), ("แก้ไข", "edit"), ("ยกเลิก", "cancel")],
            reply_token=reply_token,
        )

    def _review_create(
        self, group_id: str, user_id: str, conversation: dict, data: dict, *, reply_token: str = ""
    ) -> None:
        self._save_flow(group_id, user_id, conversation, "REVIEW_CREATE", data)
        self._buttons(
            group_id,
            f"ชื่อสินค้า : {data['name_th']}\nราคาทุน : {_format_satang(data['cost_satang'])} บาท\nราคาขาย : {data['sale_baht']} บาท\nรบกวนยืนยันรายละเอียดสินค้าให้ผมด้วยครับ 😊",
            [("ยืนยัน", "confirm"), ("แก้ไข", "edit"), ("ยกเลิก", "cancel")],
            reply_token=reply_token,
        )

    def _review_vision_existing(
        self,
        group_id: str,
        user_id: str,
        conversation: dict,
        data: dict,
        *,
        reply_token: str = "",
    ) -> None:
        self._save_flow(group_id, user_id, conversation, "VISION_EXISTING_FINAL_REVIEW", data)
        product = data["product"]
        self._buttons(
            group_id,
            f"ชื่อสินค้า : {product['name_th']}\nบาร์โค้ด : {data['barcode']}\nราคาขาย : {data['sale_baht']} บาท\nรบกวนยืนยันรายละเอียดสินค้าให้ผมด้วยครับ 😊",
            [("ยืนยัน", "confirm"), ("แก้ราคา", "edit_price"), ("ยกเลิก", "cancel")],
            reply_token=reply_token,
        )

    def _review_vision_create(
        self,
        group_id: str,
        user_id: str,
        conversation: dict,
        data: dict,
        *,
        reply_token: str = "",
    ) -> None:
        self._save_flow(group_id, user_id, conversation, "VISION_FINAL_REVIEW", data)
        self._buttons(
            group_id,
            f"ชื่อสินค้า : {data['name_th']}\nบาร์โค้ด : {data['barcode']}\nราคาขาย : {data['sale_baht']} บาท\nรบกวนยืนยันรายละเอียดสินค้าให้ผมด้วยครับ 😊",
            [("ยืนยัน", "confirm"), ("แก้ชื่อ", "edit_name"), ("แก้ราคา", "edit_price"), ("ยกเลิก", "cancel")],
            reply_token=reply_token,
        )

    def confirm_flow(
        self,
        group_id: str,
        user_id: str,
        conversation: dict,
        *,
        reply_token: str = "",
        actor_user_id: str | None = None,
    ) -> None:
        data = conversation["data"]
        state = conversation["state"]
        actor_user_id = actor_user_id or user_id
        command_id = secrets.token_urlsafe(24)
        common = {
            "command_id": command_id, "barcode": data["barcode"],
            "source": {"group_id": group_id, "line_user_id": actor_user_id},
        }
        if state == "REVIEW_PRICE":
            product = data["product"]
            command = common | {
                "operation": "update_prices", "product_uuid": product["product_uuid"],
                "expected_revision": product["revision"], "cost_satang": data["cost_satang"], "sale_baht": data["sale_baht"],
            }
        elif state == "VISION_EXISTING_FINAL_REVIEW":
            product = data["product"]
            command = common | {
                "operation": "update_prices", "product_uuid": product["product_uuid"],
                "expected_revision": product["revision"], "cost_satang": product["cost_satang"],
                "sale_baht": data["sale_baht"],
            }
        elif state == "REVIEW_CREATE":
            command = common | {
                "operation": "create_or_complete", "name_th": data["name_th"],
                "cost_satang": data["cost_satang"], "sale_baht": data["sale_baht"],
            }
            if data.get("product"):
                command |= {
                    "product_uuid": data["product"]["product_uuid"],
                    "expected_revision": data["product"]["revision"],
                }
        elif state == "VISION_FINAL_REVIEW":
            command = common | {
                "operation": "create_or_complete", "name_th": data["name_th"],
                "cost_satang": 0, "sale_baht": data["sale_baht"],
            }
            if data.get("product"):
                command |= {
                    "product_uuid": data["product"]["product_uuid"],
                    "expected_revision": data["product"]["revision"],
                }
        else:
            return
        self.store.enqueue_command(command_id, group_id, actor_user_id, command)
        self.store.close_flow(group_id, user_id)
        LOG.info("POS command queued command_id=%s operation=%s", command_id, command["operation"])
        # A Reply is free under the LINE OA plan and its one-time token is valid
        # long enough for the bounded POS request.  Return the final outcome in
        # that Reply instead of spending the monthly Push-message allowance on
        # a preliminary progress message followed by a result message.
        self.process_due_commands(limit=1, reply_tokens={command_id: reply_token})

    def _notify_command_result(self, item: dict[str, Any], outcome: str, text: str, *, reply_token: str = "") -> None:
        command_id = item["command_id"]
        if reply_token:
            try:
                self.line.reply_text(reply_token, text)
            except Exception as exc:
                LOG.warning(
                    "LINE command notification reply failed; queuing push command_id=%s outcome=%s error=%s",
                    command_id,
                    outcome,
                    exc,
                )
            else:
                LOG.info("LINE command notification delivered via reply command_id=%s outcome=%s", command_id, outcome)
                return
        notification_id = f"{command_id}:{outcome}"
        self.store.enqueue_notification(notification_id, item["group_id"], item["user_id"], text)
        LOG.info("LINE command notification queued command_id=%s notification_id=%s outcome=%s", command_id, notification_id, outcome)

    @staticmethod
    def _notification_retry_seconds(exc: Exception, default_seconds: int) -> int:
        if isinstance(exc, LineMessageRejected) and exc.status_code == 429 and "monthly limit" in str(exc).lower():
            return MONTHLY_LIMIT_NOTIFICATION_RETRY_SECONDS
        return default_seconds

    def process_due_commands(self, limit: int = 10, *, reply_tokens: dict[str, str] | None = None) -> None:
        reply_tokens = reply_tokens or {}
        for item in self.store.claim_due_commands(limit):
            reply_token = reply_tokens.get(item["command_id"], "")
            operation = item["command"].get("operation", "unknown")
            try:
                self.pos.apply(item["command"])
            except PosUnavailable as exc:
                first_outage = self.store.retry_command(item["command_id"], str(exc), self.retry_seconds)
                LOG.warning(
                    "POS command retry scheduled command_id=%s operation=%s attempts=%s error=%s",
                    item["command_id"], operation, item["attempts"], exc,
                )
                if first_outage:
                    self._notify_command_result(
                        item,
                        "retrying",
                        "ผมไม่สามารถเชื่อมต่อกับร้านได้ จะลองใหม่อีกครั้งภายหลังครับ 😥",
                        reply_token=reply_token,
                    )
            except PosRejected as exc:
                self.store.fail_command(item["command_id"], "POS rejected the command after confirmation.")
                message = (
                    "บันทึกไม่สำเร็จครับ เนื่องจากข้อมูลสินค้าถูกแก้ไขระหว่างดำเนินการ กรุณาลองใหม่อีกครั้งครับ 😥"
                    if exc.status_code == 409
                    else "บันทึกไม่สำเร็จครับ กรุณาเริ่มรายการใหม่อีกครั้งครับ 😥"
                )
                LOG.warning(
                    "POS command rejected command_id=%s operation=%s attempts=%s status_code=%s",
                    item["command_id"], operation, item["attempts"], exc.status_code,
                )
                self._notify_command_result(item, "failed", message, reply_token=reply_token)
            except Exception as exc:
                # Treat unexpected transport/client failures as retryable, and
                # retain a bounded failure detail in the durable queue.
                first_outage = self.store.retry_command(item["command_id"], repr(exc), self.retry_seconds)
                LOG.exception(
                    "POS command retry scheduled after unexpected error command_id=%s operation=%s attempts=%s",
                    item["command_id"], operation, item["attempts"],
                )
                if first_outage:
                    self._notify_command_result(
                        item,
                        "retrying",
                        "ผมไม่สามารถเชื่อมต่อกับร้านได้ จะลองใหม่อีกครั้งภายหลังครับ 😥",
                        reply_token=reply_token,
                    )
            else:
                self.store.complete_command(item["command_id"])
                LOG.info("POS command applied command_id=%s operation=%s attempts=%s", item["command_id"], operation, item["attempts"])
                self._notify_command_result(
                    item,
                    "applied",
                    "ดำเนินการอัพเดตข้อมูลเรียบร้อยแล้วครับ ✅",
                    reply_token=reply_token,
                )

    def process_due_notifications(self, limit: int = 10) -> None:
        """Deliver deferred outcome notices without allowing LINE failures to affect POS state."""

        for item in self.store.claim_due_notifications(limit):
            try:
                self.line.push_text(
                    item["group_id"],
                    item["text"],
                    mention_user_id=item["user_id"],
                    retry_key=item["retry_key"],
                )
            except LineMessageRejected as exc:
                if exc.status_code == 409:
                    # LINE accepted an earlier request with this retry key.
                    self.store.complete_notification(item["notification_id"])
                    LOG.info("LINE notification previously accepted notification_id=%s", item["notification_id"])
                elif exc.status_code in {400, 401, 403}:
                    self.store.fail_notification(item["notification_id"], str(exc))
                    LOG.error("LINE notification rejected permanently notification_id=%s error=%s", item["notification_id"], exc)
                else:
                    retry_seconds = self._notification_retry_seconds(exc, self.retry_seconds)
                    self.store.retry_notification(item["notification_id"], str(exc), retry_seconds)
                    LOG.warning(
                        "LINE notification retry scheduled notification_id=%s attempts=%s delay_seconds=%s error=%s",
                        item["notification_id"], item["attempts"], retry_seconds, exc,
                    )
            except Exception as exc:
                self.store.retry_notification(item["notification_id"], repr(exc), self.retry_seconds)
                LOG.exception(
                    "LINE notification retry scheduled after unexpected error notification_id=%s attempts=%s",
                    item["notification_id"], item["attempts"],
                )
            else:
                self.store.complete_notification(item["notification_id"])
                LOG.info("LINE notification delivered via push notification_id=%s attempts=%s", item["notification_id"], item["attempts"])

    def expire_flows(self) -> None:
        for expired in self.store.expire_flows():
            try:
                self.line.push_text(
                    expired["group_id"],
                    "ผมยกเลิกรายการแล้วเนื่องจากเกินเวลาที่กำหนด กรุณาทำรายการใหม่อีกครั้งครับ ⏰",
                    mention_user_id=expired["user_id"],
                )
            except Exception:
                LOG.warning("Could not send LINE Bot flow-timeout notification", exc_info=True)
