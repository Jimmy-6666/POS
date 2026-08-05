import base64
import hashlib
import hmac
import json
import tempfile
import time
import unittest
from pathlib import Path

from line_bot.app import BackgroundWorker, create_app
from line_bot.clients import LineMessageRejected, LineMessagingClient, PosRejected, PosUnavailable
from line_bot.config import BotSettings
from line_bot.storage import BotStore, FLOW_TIMEOUT, iso_now
from line_bot.workflow import BotWorkflow
from line_bot.workflow import ZxingBarcodeDecoder


class FakeLine:
    def __init__(self):
        self.replies = []
        self.button_reply_tokens = []
        self.texts = []
        self.buttons = []
        self.contents = {"image-1": b"barcode-source"}

    def reply_text(self, reply_token, text):
        self.replies.append((reply_token, text))

    def push_text(self, group_id, text, *, mention_user_id=None, retry_key=None):
        self.texts.append((group_id, text, mention_user_id, retry_key))

    def push_buttons(self, group_id, text, actions):
        self.buttons.append((group_id, text, actions))

    def reply_buttons(self, reply_token, text, actions):
        self.button_reply_tokens.append(reply_token)
        self.buttons.append(("reply", text, actions))

    def message_content(self, message_id):
        return self.contents[message_id]


class FakeDecoder:
    def decode(self, image_bytes):
        return "BOT-001" if image_bytes == b"barcode-source" else None


class FakePos:
    def __init__(self, product=None):
        self.product = product or {
            "product_uuid": "product-uuid-1", "revision": "revision-1", "name_th": "สินค้าทดสอบ",
            "cost_baht": "10.00", "cost_satang": 1000, "sale_baht": 20, "has_image": False, "is_placeholder": False,
        }
        self.applied = []
        self.unavailable = False
        self.rejected = False
        self.rejected_status = 409
        self.cleaned = 0

    def lookup(self, barcode):
        return {"barcode": barcode, "product": self.product}

    def apply(self, command):
        if self.unavailable:
            raise PosUnavailable("offline")
        if self.rejected:
            raise PosRejected("rejected", status_code=self.rejected_status)
        self.applied.append(command)
        return {"ok": True}


class LineBotWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = BotStore(Path(self.temp.name))
        self.line = FakeLine()
        self.pos = FakePos()
        self.workflow = BotWorkflow(self.store, self.line, self.pos, FakeDecoder(), retry_seconds=300)
        self.group_id = "C-test-group"
        self.user_id = "U-test-manager"

    def tearDown(self):
        self.temp.cleanup()

    def image_event(self, message_id="image-1", *, user_id=None):
        return {"type": "message", "source": {"type": "group", "groupId": self.group_id, "userId": user_id or self.user_id},
                "message": {"type": "image", "id": message_id}}

    def quote_event(self, *, user_id=None, quote_id="image-1"):
        return {"type": "message", "replyToken": "reply-1",
                "source": {"type": "group", "groupId": self.group_id, "userId": user_id or self.user_id},
                "message": {"type": "text", "id": "quote-1", "text": "บอท", "quotedMessageId": quote_id}}

    def button_event(self, text, *, user_id=None):
        return {"type": "message", "replyToken": f"reply-button-{text}",
                "source": {"type": "group", "groupId": self.group_id, "userId": user_id or self.user_id},
                "message": {"type": "text", "id": f"button-{text}", "text": text}}

    def current_action(self, name):
        for label in self.line.buttons[-1][2]:
            if label == name:
                return label
        self.fail(f"Missing action {name}")

    def test_existing_product_price_flow_is_group_shared_and_records_actual_confirmer(self):
        self.workflow.handle_event(self.image_event())
        self.workflow.handle_event(self.quote_event())
        self.assertEqual(self.line.button_reply_tokens[-1], "reply-1")
        self.assertEqual(
            self.line.buttons[-1][1],
            "พบสินค้าในระบบแล้วครับ 😊\nชื่อสินค้า : สินค้าทดสอบ\nราคาทุน : 10.00 บาท\nราคาขาย : 20 บาท\nต้องการทำรายการใดครับ",
        )
        self.assertEqual(self.line.buttons[-1][2], ["แก้ราคาทุน/ราคาขาย"])
        price_action = self.current_action("แก้ราคาทุน/ราคาขาย")
        cashier_id = "U-other"
        self.workflow.handle_event(self.button_event(price_action, user_id=cashier_id))
        self.assertEqual(self.store.conversation(self.group_id, self.user_id)["state"], "PRICE_COST")
        self.assertEqual(
            self.line.replies[-1][1],
            "แก้ราคาทุนเป็นเท่าไหร่ดีครับ\n(หากไม่ทราบระบุ 0) 😊",
        )
        self.workflow.handle_text_input(self.group_id, cashier_id, "15.50")
        self.workflow.handle_text_input(self.group_id, cashier_id, "25")
        confirm = self.current_action("ยืนยัน")
        self.workflow.handle_event(self.button_event(confirm, user_id=cashier_id))
        self.assertEqual(len(self.pos.applied), 1)
        command = self.pos.applied[0]
        self.assertEqual(command["operation"], "update_prices")
        self.assertEqual((command["cost_satang"], command["sale_baht"]), (1550, 25))
        self.assertEqual(command["source"]["line_user_id"], cashier_id)
        self.assertIsNone(self.store.conversation(self.group_id, self.user_id))
        self.assertEqual(self.line.replies[-1][1], "ดำเนินการอัพเดตข้อมูลเรียบร้อยแล้วครับ ✅")
        self.assertFalse(any("ดำเนินการอัพเดตข้อมูลเรียบร้อยแล้วครับ" in text for _, text, *_ in self.line.texts))

    def test_group_member_can_quote_another_members_image_and_share_the_flow(self):
        cashier_id = "U-test-cashier"
        self.workflow.handle_event(self.image_event(user_id=cashier_id))
        self.workflow.handle_event(self.quote_event())

        conversation = self.store.conversation(self.group_id, self.user_id)
        self.assertEqual(conversation["state"], "EXISTING_CHOICE")
        self.assertEqual(conversation["data"]["source_image_id"], "image-1")
        price_action = self.current_action("แก้ราคาทุน/ราคาขาย")

        self.workflow.handle_event(self.button_event(price_action, user_id=cashier_id))
        self.assertEqual(self.store.conversation(self.group_id, self.user_id)["state"], "PRICE_COST")
        self.workflow.handle_text_input(self.group_id, self.user_id, "15.00")
        self.assertEqual(self.store.conversation(self.group_id, self.user_id)["state"], "PRICE_SALE")

    def test_quote_cannot_use_an_image_from_a_different_group(self):
        self.store.remember_source_image("other-group-image", "C-other", "U-test-cashier")
        self.workflow.handle_event(self.quote_event(quote_id="other-group-image"))
        self.assertIsNone(self.store.conversation(self.group_id, self.user_id))
        self.assertIn("ในกลุ่มนี้", self.line.texts[-1][1])

    def test_new_quote_does_not_replace_an_active_group_legacy_flow(self):
        cashier_id = "U-test-cashier"
        self.workflow.handle_event(self.image_event())
        self.workflow.handle_event(self.quote_event())
        self.line.contents["image-2"] = b"barcode-source"
        self.workflow.handle_event(self.image_event("image-2", user_id=cashier_id))
        self.workflow.handle_event(self.quote_event(user_id=cashier_id, quote_id="image-2"))

        conversation = self.store.conversation(self.group_id, self.user_id)
        self.assertEqual(conversation["state"], "EXISTING_CHOICE")
        self.assertEqual(conversation["data"]["source_image_id"], "image-1")
        self.assertIn("กำลังดำเนินการอยู่", self.line.replies[-1][1])

    def test_legacy_pos_summary_without_cost_satang_still_starts_the_flow(self):
        self.pos.product.pop("cost_satang")
        self.pos.product["cost_baht"] = "10.25"
        self.workflow.handle_event(self.image_event())
        self.workflow.handle_event(self.quote_event())
        self.assertIn("ราคาทุน : 10.25 บาท", self.line.buttons[-1][1])
        conversation = self.store.conversation(self.group_id, self.user_id)
        self.assertEqual(conversation["data"]["product"]["cost_satang"], 1025)

    def test_placeholder_follows_add_product_flow_without_new_image(self):
        self.pos.product["is_placeholder"] = True
        self.pos.product["name_th"] = "สินค้าไม่ทราบชื่อ (BOT-001)"
        self.workflow.handle_event(self.image_event())
        self.workflow.handle_event(self.quote_event())
        self.workflow.handle_event(self.button_event(self.current_action("เพิ่มสินค้า")))
        self.workflow.handle_text_input(self.group_id, self.user_id, "ชื่อที่ถูกต้อง")
        self.assertEqual(
            self.line.texts[-1][1],
            "สินค้านี้ต้นทุนเท่าไหร่ครับ\n(หากไม่ทราบระบุ 0) 😊",
        )
        self.workflow.handle_text_input(self.group_id, self.user_id, "0")
        self.workflow.handle_text_input(self.group_id, self.user_id, "35")
        self.assertNotIn("ต้องการเพิ่มรูปไหมครับ", self.line.buttons[-1][1])
        self.workflow.handle_event(self.button_event(self.current_action("ยืนยัน")))
        self.assertEqual(self.line.replies[-1][1], "ดำเนินการอัพเดตข้อมูลเรียบร้อยแล้วครับ ✅")
        command = self.pos.applied[0]
        self.assertEqual(command["operation"], "create_or_complete")
        self.assertEqual(command["name_th"], "ชื่อที่ถูกต้อง")

    def test_connectivity_failure_is_durable_and_retries_to_success(self):
        self.pos.unavailable = True
        self.workflow.handle_event(self.image_event())
        self.workflow.handle_event(self.quote_event())
        self.workflow.handle_event(self.button_event(self.current_action("แก้ราคาทุน/ราคาขาย")))
        self.workflow.handle_text_input(self.group_id, self.user_id, "0")
        self.workflow.handle_text_input(self.group_id, self.user_id, "12")
        self.workflow.handle_event(self.button_event(self.current_action("ยืนยัน")))
        with self.store.session() as db:
            pending = db.execute("SELECT command_id,status,last_error FROM pending_commands").fetchone()
            self.assertEqual(pending["status"], "retry_wait")
            self.assertIn("offline", pending["last_error"])
            db.execute("UPDATE pending_commands SET next_attempt_at=?", (iso_now(),))
        self.pos.unavailable = False
        self.workflow.process_due_commands()
        with self.store.session() as db:
            self.assertEqual(db.execute("SELECT status FROM pending_commands").fetchone()[0], "applied")
        self.assertEqual(len(self.pos.applied), 1)
        self.workflow.process_due_notifications()
        self.assertIn("ดำเนินการอัพเดตข้อมูลเรียบร้อยแล้วครับ", self.line.texts[-1][1])
        self.assertIsNotNone(self.line.texts[-1][3])

    def test_confirm_rejection_tells_user_to_retry(self):
        self.pos.rejected = True
        self.workflow.handle_event(self.image_event())
        self.workflow.handle_event(self.quote_event())
        self.workflow.handle_event(self.button_event(self.current_action("แก้ราคาทุน/ราคาขาย")))
        self.workflow.handle_text_input(self.group_id, self.user_id, "0")
        self.workflow.handle_text_input(self.group_id, self.user_id, "12")
        self.workflow.handle_event(self.button_event(self.current_action("ยืนยัน")))
        self.assertIn("บันทึกไม่สำเร็จครับ", self.line.replies[-1][1])
        self.assertIn("กรุณาลองใหม่อีกครั้ง", self.line.replies[-1][1])

    def test_non_conflict_rejection_does_not_claim_the_product_was_changed(self):
        self.pos.rejected = True
        self.pos.rejected_status = 400
        self.workflow.handle_event(self.image_event())
        self.workflow.handle_event(self.quote_event())
        self.workflow.handle_event(self.button_event(self.current_action("แก้ราคาทุน/ราคาขาย")))
        self.workflow.handle_text_input(self.group_id, self.user_id, "0")
        self.workflow.handle_text_input(self.group_id, self.user_id, "12")
        self.workflow.handle_event(self.button_event(self.current_action("ยืนยัน")))
        self.assertEqual(
            self.line.replies[-1][1],
            "บันทึกไม่สำเร็จครับ กรุณาเริ่มรายการใหม่อีกครั้งครับ 😥",
        )

    def test_barcode_decode_timeout_replies_with_clear_retry_message(self):
        class SlowDecoder:
            def decode(self, image_bytes):
                time.sleep(0.2)
                return "LATE-BARCODE"

        workflow = BotWorkflow(
            self.store,
            self.line,
            self.pos,
            SlowDecoder(),
            retry_seconds=300,
            barcode_timeout_seconds=0.01,
        )
        workflow.handle_event(self.image_event())
        started = time.monotonic()
        workflow.handle_event(self.quote_event())
        self.assertLess(time.monotonic() - started, 0.15)
        self.assertIn("ภายใน 10 วินาที", self.line.replies[-1][1])

    def test_cost_accepts_satang_and_sale_validation_explains_the_reason(self):
        self.workflow.handle_event(self.image_event())
        self.workflow.handle_event(self.quote_event())
        self.workflow.handle_event(self.button_event(self.current_action("แก้ราคาทุน/ราคาขาย")))
        self.workflow.handle_text_input(self.group_id, self.user_id, "10.50")
        self.workflow.handle_text_input(self.group_id, self.user_id, "0")
        self.assertEqual(self.line.texts[-1][1], "กรุณาระบุราคาขายให้เกิน 0 บาท 😊")
        self.workflow.handle_text_input(self.group_id, self.user_id, "10")
        self.assertEqual(
            self.line.texts[-1][1],
            "กรุณาระบุราคาขาย ที่มากกว่าราคาทุน 10.50 บาท 😊",
        )
        self.workflow.handle_text_input(self.group_id, self.user_id, "11")
        self.assertIn("ราคาทุน : 10.50 บาท", self.line.buttons[-1][1])

    def test_expired_flow_is_closed_and_notifies_the_owner_after_one_minute(self):
        self.assertEqual(FLOW_TIMEOUT.total_seconds(), 60)
        self.workflow.handle_event(self.image_event())
        self.workflow.handle_event(self.quote_event())
        with self.store.session() as db:
            db.execute(
                """UPDATE conversations
                   SET expires_at='2999-01-01T00:00:00+00:00',updated_at='2000-01-01T00:00:00+00:00'
                   WHERE group_id=? AND user_id=?""",
                (self.group_id, self.user_id),
            )
        self.workflow.expire_flows()
        self.assertIsNone(self.store.conversation(self.group_id, self.user_id))
        self.assertEqual(
            self.line.texts[-1][1],
            "ผมยกเลิกรายการแล้วเนื่องจากเกินเวลาที่กำหนด กรุณาทำรายการใหม่อีกครั้งครับ ⏰",
        )
        self.assertEqual(self.line.texts[-1][2], self.user_id)

    def test_monthly_limit_keeps_a_deferred_outcome_notification_for_retry(self):
        class MonthlyLimitLine(FakeLine):
            def push_text(self, group_id, text, *, mention_user_id=None, retry_key=None):
                raise LineMessageRejected(
                    'LINE Messaging API 429: {"message":"You have reached your monthly limit."}',
                    status_code=429,
                )

        workflow = BotWorkflow(self.store, MonthlyLimitLine(), self.pos, FakeDecoder(), retry_seconds=300)
        self.store.enqueue_notification("command-1:applied", self.group_id, self.user_id, "บันทึกสำเร็จ")
        with self.assertLogs("line_bot.workflow", level="WARNING") as logs:
            workflow.process_due_notifications()
        self.assertIn("delay_seconds=3600", "\n".join(logs.output))
        with self.store.session() as db:
            notification = db.execute(
                "SELECT status,last_error FROM pending_notifications WHERE notification_id='command-1:applied'"
            ).fetchone()
        self.assertEqual(notification["status"], "pending")
        self.assertIn("monthly limit", notification["last_error"])

    def test_buttons_send_visible_message_actions(self):
        class CapturingLineClient(LineMessagingClient):
            def __init__(self):
                super().__init__("line-access-token-for-tests")
                self.sent = []

            def _post(self, path, payload):
                self.sent.append((path, payload))

        client = CapturingLineClient()
        client.push_buttons(self.group_id, "เลือกการทำงาน", ["ยืนยัน", "ยกเลิก"])
        actions = client.sent[0][1]["messages"][0]["template"]["actions"]
        self.assertEqual(
            actions,
            [
                {"type": "message", "label": "ยืนยัน", "text": "ยืนยัน"},
                {"type": "message", "label": "ยกเลิก", "text": "ยกเลิก"},
            ],
        )

    def test_rejected_mention_falls_back_to_plain_group_text(self):
        class FallbackLineClient(LineMessagingClient):
            def __init__(self):
                super().__init__("line-access-token-for-tests")
                self.sent = []

            def _post(self, path, payload, *, retry_key=None):
                self.sent.append((path, payload))
                message_type = payload["messages"][0]["type"]
                if message_type == "textV2":
                    raise LineMessageRejected("LINE Messaging API 400: mention rejected", status_code=400)

        client = FallbackLineClient()
        with self.assertLogs("line_bot.clients", level="WARNING"):
            client.push_text(self.group_id, "บันทึกสำเร็จ", mention_user_id=self.user_id)
        self.assertEqual(
            [payload["messages"][0]["type"] for _, payload in client.sent],
            ["textV2", "text"],
        )

    def test_push_mention_uses_the_current_line_message_shape_and_retry_key(self):
        class CapturingLineClient(LineMessagingClient):
            def __init__(self):
                super().__init__("line-access-token-for-tests")
                self.sent = []

            def _post(self, path, payload, *, retry_key=None):
                self.sent.append((path, payload, retry_key))

        client = CapturingLineClient()
        client.push_text(self.group_id, "บันทึกสำเร็จ", mention_user_id=self.user_id, retry_key="retry-key-123")
        _, payload, retry_key = client.sent[0]
        mentionee = payload["messages"][0]["substitution"]["user"]["mentionee"]
        self.assertEqual(mentionee, {"type": "user", "userId": self.user_id})
        self.assertEqual(retry_key, "retry-key-123")

    def test_zxing_decoder_reads_a_linear_barcode_and_rejects_qr_code(self):
        from io import BytesIO
        import qrcode
        import zxingcpp
        from PIL import Image

        barcode_image = Image.fromarray(
            zxingcpp.write_barcode(zxingcpp.BarcodeFormat.Code128, "BOT-CODE-123")
        )
        binary = BytesIO()
        barcode_image.save(binary, format="PNG")
        decoder = ZxingBarcodeDecoder()
        self.assertEqual(decoder.decode(binary.getvalue()), "BOT-CODE-123")

        qr_image = qrcode.make("QR-MUST-NOT-BE-ACCEPTED")
        binary = BytesIO()
        qr_image.save(binary, format="PNG")
        self.assertIsNone(decoder.decode(binary.getvalue()))


class LineBotWebhookTests(unittest.TestCase):
    def test_worker_purges_source_image_references_after_24_hours(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = BotSettings(
                channel_secret="line-channel-secret-for-tests", channel_access_token="line-access-token-for-tests",
                allowed_group_ids=frozenset({"C-allowed"}), bot_user_id="U-bot",
                pos_base_url="https://pos.example.test", pos_shared_secret="x" * 32,
                data_root=Path(temporary),
            )
            app = create_app(settings, line_client=FakeLine(), pos_client=FakePos(), decoder=FakeDecoder(), start_worker=False)
            store = app.config["BOT_STORE"]
            store.remember_source_image("expired-image", "C-allowed", "U-1")
            store.remember_source_image("fresh-image", "C-allowed", "U-1")
            with store.session() as db:
                db.execute("UPDATE source_images SET received_at='2000-01-01T00:00:00+00:00' WHERE message_id='expired-image'")
            self.assertIsNone(store.source_image("expired-image"))
            app.extensions["line_bot_worker"].process_once()
            with store.session() as db:
                remaining = [row[0] for row in db.execute("SELECT message_id FROM source_images ORDER BY message_id")]
            self.assertEqual(remaining, ["fresh-image"])

    def test_webhook_verification_stores_only_allowed_group_events(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = BotSettings(
                channel_secret="line-channel-secret-for-tests", channel_access_token="line-access-token-for-tests",
                allowed_group_ids=frozenset({"C-allowed"}), bot_user_id="U-bot",
                pos_base_url="https://pos.example.test", pos_shared_secret="x" * 32,
                data_root=Path(temporary),
            )
            app = create_app(settings, line_client=FakeLine(), pos_client=FakePos(), decoder=FakeDecoder(), start_worker=False)
            client = app.test_client()
            payload = {"events": [
                {"webhookEventId": "event-ok", "type": "message", "source": {"type": "group", "groupId": "C-allowed", "userId": "U-1"}, "message": {"type": "image", "id": "i-1"}},
                {"webhookEventId": "event-no", "type": "message", "source": {"type": "group", "groupId": "C-no", "userId": "U-2"}, "message": {"type": "image", "id": "i-2"}},
            ]}
            raw = json.dumps(payload).encode("utf-8")
            signature = base64.b64encode(hmac.new(settings.channel_secret.encode(), raw, hashlib.sha256).digest()).decode()
            response = client.post("/webhook", data=raw, content_type="application/json", headers={"X-Line-Signature": signature})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["accepted"], 1)
            worker = app.extensions["line_bot_worker"]
            worker.process_once()
            with app.config["BOT_STORE"].session() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM source_images").fetchone()[0], 1)

    def test_enrollment_mode_records_group_without_processing_the_event(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = BotSettings(
                channel_secret="line-channel-secret-for-tests", channel_access_token="line-access-token-for-tests",
                # Enrollment has precedence even when this group had already
                # been allowlisted, so no legacy event can produce a write.
                allowed_group_ids=frozenset({"C-enroll"}), bot_user_id="U-bot",
                pos_base_url="https://pos.example.test", pos_shared_secret="x" * 32,
                data_root=Path(temporary), enrollment_mode=True,
            )
            app = create_app(settings, line_client=FakeLine(), pos_client=FakePos(), decoder=FakeDecoder(), start_worker=False)
            payload = {"events": [{"webhookEventId": "enroll", "type": "message", "source": {"type": "group", "groupId": "C-enroll", "userId": "U-1"}, "message": {"type": "image", "id": "i-1"}}]}
            raw = json.dumps(payload).encode("utf-8")
            signature = base64.b64encode(hmac.new(settings.channel_secret.encode(), raw, hashlib.sha256).digest()).decode()
            response = app.test_client().post("/webhook", data=raw, content_type="application/json", headers={"X-Line-Signature": signature})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.get_json()["accepted"], 0)
            with app.config["BOT_STORE"].session() as db:
                self.assertEqual(db.execute("SELECT group_id FROM enrollment_groups").fetchone()[0], "C-enroll")
                self.assertEqual(db.execute("SELECT COUNT(*) FROM webhook_events").fetchone()[0], 0)
