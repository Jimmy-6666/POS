"""LINE group conversation state machine and durable POS retry worker."""

from __future__ import annotations

import secrets
import threading
import logging
import re
from typing import Any, Protocol

from .clients import PosRejected, PosUnavailable


LOG = logging.getLogger(__name__)


class BarcodeDecoder(Protocol):
    def decode(self, image_bytes: bytes) -> str | None: ...


class ZxingBarcodeDecoder:
    """Decode linear retail barcodes, but never QR or other matrix codes."""

    def decode(self, image_bytes: bytes) -> str | None:
        try:
            import zxingcpp
            from PIL import Image
        except ImportError as exc:
            raise RuntimeError("Barcode decoder dependencies are not installed.") from exc
        from io import BytesIO

        results = zxingcpp.read_barcodes(
            Image.open(BytesIO(image_bytes)),
            formats=zxingcpp.BarcodeFormat.LinearCodes,
        )
        return next((str(item.text).strip() for item in results if str(item.text).strip()), None)


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
    ):
        self.store = store
        self.line = line_client
        self.pos = pos_client
        self.decoder = decoder
        self.retry_seconds = retry_seconds
        self.barcode_timeout_seconds = barcode_timeout_seconds

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
            if message_id:
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

    def start_quoted_image(self, event: dict, group_id: str, user_id: str, quote_id: str) -> None:
        original = self.store.source_image(quote_id)
        if not original or original["group_id"] != group_id or original["user_id"] != user_id:
            self.line.push_text(group_id, "กรุณา Quote รูปบาร์โค้ดที่คุณส่งเอง แล้วเรียกบอทอีกครั้งครับ 😊")
            return
        reply_token = str(event.get("replyToken") or "")
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
    ) -> None:
        state = conversation["state"]
        data = conversation["data"]
        if action == "cancel":
            self.store.close_flow(group_id, user_id)
            self.line.push_text(group_id, "ผมยกเลิกรายการเปลี่ยนแปลงแล้วครับ 🌷")
            return
        if state == "EXISTING_CHOICE" and action == "prices":
            self._save_flow(group_id, user_id, conversation, "PRICE_COST", data)
            self.line.push_text(group_id, "แก้ราคาทุนเป็นเท่าไหร่ดีครับ\n(หากไม่ทราบระบุ 0) 😊")
        elif state == "OFFER_CREATE" and action == "add":
            self._save_flow(group_id, user_id, conversation, "CREATE_NAME", data)
            self.line.push_text(group_id, "สินค้านี้ชื่ออะไรครับ 😊")
        elif state in {"REVIEW_PRICE", "REVIEW_CREATE"} and action == "confirm":
            self.confirm_flow(group_id, user_id, conversation, reply_token=reply_token)
        elif state == "REVIEW_PRICE" and action == "edit":
            data.pop("cost_satang", None)
            data.pop("sale_baht", None)
            self._save_flow(group_id, user_id, conversation, "PRICE_COST", data)
            self.line.push_text(group_id, "แก้ราคาทุนเป็นเท่าไหร่ดีครับ\n(หากไม่ทราบระบุ 0) 😊")
        elif state == "REVIEW_CREATE" and action == "edit":
            self._save_flow(group_id, user_id, conversation, "CREATE_NAME", data)
            self.line.push_text(group_id, "สินค้านี้ชื่ออะไรครับ 😊")

    def handle_text_input(self, group_id: str, user_id: str, text: str, *, reply_token: str = "") -> None:
        conversation = self.store.conversation(group_id, user_id)
        if not conversation:
            return
        state, data = conversation["state"], conversation["data"]
        action = self.MESSAGE_ACTIONS.get(state, {}).get(text.strip())
        if action:
            self.handle_flow_action(group_id, user_id, conversation, action, reply_token=reply_token)
            return
        if state == "PRICE_COST":
            cost = _cost_satang(text)
            if cost is None:
                self._save_flow(group_id, user_id, conversation, state, data)
                self.line.push_text(group_id, "กรุณาระบุราคาทุนเป็นจำนวนบาทและสตางค์ไม่เกิน 2 ตำแหน่งครับ 😊")
                return
            data["cost_satang"] = cost
            self._save_flow(group_id, user_id, conversation, "PRICE_SALE", data)
            self.line.push_text(group_id, "แก้ราคาขายเป็นเท่าไหร่ดีครับ 😊")
        elif state == "PRICE_SALE":
            sale = _whole_baht(text, positive=True)
            if sale is None:
                self._save_flow(group_id, user_id, conversation, state, data)
                self.line.push_text(group_id, "กรุณาระบุราคาขายให้เกิน 0 บาท 😊")
                return
            if data.get("cost_satang", 0) and sale * 100 <= data["cost_satang"]:
                self._save_flow(group_id, user_id, conversation, state, data)
                self.line.push_text(
                    group_id,
                    f"กรุณาระบุราคาขาย ที่มากกว่าราคาทุน {_format_satang(data['cost_satang'])} บาท 😊",
                )
                return
            data["sale_baht"] = sale
            self._review_price(group_id, user_id, conversation, data)
        elif state == "CREATE_NAME":
            name = text.strip()
            if not name or len(name) > 160 or name.startswith("สินค้าไม่ทราบชื่อ ("):
                self._save_flow(group_id, user_id, conversation, state, data)
                self.line.push_text(group_id, "กรุณาระบุชื่อสินค้าที่ถูกต้อง ไม่เกิน 160 ตัวอักษรครับ 😊")
                return
            data["name_th"] = name
            self._save_flow(group_id, user_id, conversation, "CREATE_COST", data)
            self.line.push_text(group_id, "สินค้านี้ต้นทุนเท่าไหร่ครับ\n(หากไม่ทราบระบุ 0) 😊")
        elif state == "CREATE_COST":
            cost = _cost_satang(text)
            if cost is None:
                self._save_flow(group_id, user_id, conversation, state, data)
                self.line.push_text(group_id, "กรุณาระบุต้นทุนเป็นจำนวนบาทและสตางค์ไม่เกิน 2 ตำแหน่งครับ 😊")
                return
            data["cost_satang"] = cost
            self._save_flow(group_id, user_id, conversation, "CREATE_SALE", data)
            self.line.push_text(group_id, "สินค้านี้ราคาขายเท่าไหร่ครับ 😊")
        elif state == "CREATE_SALE":
            sale = _whole_baht(text, positive=True)
            if sale is None:
                self._save_flow(group_id, user_id, conversation, state, data)
                self.line.push_text(group_id, "กรุณาระบุราคาขายให้เกิน 0 บาท 😊")
                return
            if data.get("cost_satang", 0) and sale * 100 <= data["cost_satang"]:
                self._save_flow(group_id, user_id, conversation, state, data)
                self.line.push_text(
                    group_id,
                    f"กรุณาระบุราคาขาย ที่มากกว่าราคาทุน {_format_satang(data['cost_satang'])} บาท 😊",
                )
                return
            data["sale_baht"] = sale
            self._review_create(group_id, user_id, conversation, data)

    def _review_price(self, group_id: str, user_id: str, conversation: dict, data: dict) -> None:
        self._save_flow(group_id, user_id, conversation, "REVIEW_PRICE", data)
        product = data["product"]
        self._buttons(
            group_id,
            f"ชื่อสินค้า : {product['name_th']}\nราคาทุน : {_format_satang(data['cost_satang'])} บาท\nราคาขาย : {data['sale_baht']} บาท\nรบกวนยืนยันรายละเอียดให้ผมด้วยครับ 😊",
            [("ยืนยัน", "confirm"), ("แก้ไข", "edit"), ("ยกเลิก", "cancel")],
        )

    def _review_create(self, group_id: str, user_id: str, conversation: dict, data: dict) -> None:
        self._save_flow(group_id, user_id, conversation, "REVIEW_CREATE", data)
        self._buttons(
            group_id,
            f"ชื่อสินค้า : {data['name_th']}\nราคาทุน : {_format_satang(data['cost_satang'])} บาท\nราคาขาย : {data['sale_baht']} บาท\nรบกวนยืนยันรายละเอียดสินค้าให้ผมด้วยครับ 😊",
            [("ยืนยัน", "confirm"), ("แก้ไข", "edit"), ("ยกเลิก", "cancel")],
        )

    def confirm_flow(self, group_id: str, user_id: str, conversation: dict, *, reply_token: str = "") -> None:
        data = conversation["data"]
        state = conversation["state"]
        command_id = secrets.token_urlsafe(24)
        common = {
            "command_id": command_id, "barcode": data["barcode"],
            "source": {"group_id": group_id, "line_user_id": user_id},
        }
        if state == "REVIEW_PRICE":
            product = data["product"]
            command = common | {
                "operation": "update_prices", "product_uuid": product["product_uuid"],
                "expected_revision": product["revision"], "cost_satang": data["cost_satang"], "sale_baht": data["sale_baht"],
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
        else:
            return
        self.store.enqueue_command(command_id, group_id, user_id, command)
        self.store.close_flow(group_id, user_id)
        # Reply before the bounded POS request so LINE receives a status well
        # within the 55-second reply window for the user's confirmation event.
        self._reply_or_push_text(reply_token, group_id, "ผมกำลังทำการเชื่อมต่อกับร้านเพื่อแก้ไขข้อมูลครับ ⏳")
        self.process_due_commands(limit=1)

    def process_due_commands(self, limit: int = 10) -> None:
        for item in self.store.claim_due_commands(limit):
            try:
                self.pos.apply(item["command"])
            except PosUnavailable as exc:
                first_outage = self.store.retry_command(item["command_id"], str(exc), self.retry_seconds)
                if first_outage:
                    self.line.push_text(
                        item["group_id"],
                        "ผมไม่สามารถเชื่อมต่อกับร้านได้ จะลองใหม่อีกครั้งภายหลังครับ 😥",
                        mention_user_id=item["user_id"],
                    )
            except PosRejected as exc:
                self.store.fail_command(item["command_id"], "POS rejected the command after confirmation.")
                message = (
                    "บันทึกไม่สำเร็จครับ เนื่องจากข้อมูลสินค้าถูกแก้ไขระหว่างดำเนินการ กรุณาลองใหม่อีกครั้งครับ 😥"
                    if exc.status_code == 409
                    else "บันทึกไม่สำเร็จครับ กรุณาเริ่มรายการใหม่อีกครั้งครับ 😥"
                )
                self.line.push_text(
                    item["group_id"],
                    message,
                    mention_user_id=item["user_id"],
                )
            except Exception as exc:
                # Treat unexpected transport/client failures as retryable, and
                # retain a bounded failure detail in the durable queue.
                first_outage = self.store.retry_command(item["command_id"], repr(exc), self.retry_seconds)
                if first_outage:
                    self.line.push_text(item["group_id"], "ผมไม่สามารถเชื่อมต่อกับร้านได้ จะลองใหม่อีกครั้งภายหลังครับ 😥", mention_user_id=item["user_id"])
            else:
                self.store.complete_command(item["command_id"])
                self.line.push_text(
                    item["group_id"], "ดำเนินการอัพเดตข้อมูลเรียบร้อยแล้วครับ ✅", mention_user_id=item["user_id"],
                )

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
