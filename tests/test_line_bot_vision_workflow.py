import base64
import hashlib
import hmac
import json
import sys
import tempfile
import types
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from line_bot.app import BackgroundWorker, VisionWorker, create_app
from line_bot.clients import PosUnavailable
from line_bot.config import BotSettings
from line_bot.storage import BotStore, iso_now
from line_bot.vision import (
    MAX_GEMINI_RESPONSE_TOKENS,
    GeminiUsage,
    GoogleProductVisionClient,
    ProductVisionResult,
    VisionError,
    VisionRetryableError,
)
from line_bot.workflow import BotWorkflow


def png_bytes(color):
    image = Image.new("RGB", (12, 12), color)
    output = BytesIO()
    try:
        image.save(output, format="PNG")
        return output.getvalue()
    finally:
        image.close()
        output.close()


class FakeLine:
    def __init__(self):
        self.replies = []
        self.button_reply_tokens = []
        self.texts = []
        self.buttons = []
        self.contents = {}

    def reply_text(self, reply_token, text):
        self.replies.append((reply_token, text))

    def push_text(self, group_id, text, *, mention_user_id=None, retry_key=None):
        self.texts.append((group_id, text, mention_user_id, retry_key))

    def push_buttons(self, group_id, text, labels):
        self.buttons.append((group_id, text, labels))

    def reply_buttons(self, reply_token, text, labels):
        self.button_reply_tokens.append(reply_token)
        self.buttons.append(("reply", text, labels))

    def message_content(self, message_id):
        return self.contents[message_id]


class FakeDecoder:
    def __init__(self):
        self.results = {}

    def decode(self, image_bytes):
        return next(iter(self.decode_all(image_bytes)), None)

    def decode_all(self, image_bytes):
        return set(self.results.get(image_bytes, set()))


class FakeVision:
    def __init__(self, result=None, error=None):
        self.result = result or ProductVisionResult(
            same_product=True,
            suggested_name_th="แบรนด์ น้ำผลไม้ ส้ม 250 มล.",
            brand="แบรนด์",
            product_type="น้ำผลไม้",
            variant="ส้ม",
            size="250 มล.",
            confidence=0.9,
            warnings=(),
        )
        self.error = error
        self.calls = []

    def analyze_product(self, images):
        self.calls.append(list(images))
        if self.error:
            raise self.error
        return self.result


class FakePos:
    def __init__(self, product=None):
        self.product = product
        self.lookups = []
        self.applied = []
        self.unavailable = False

    def lookup(self, barcode):
        self.lookups.append(barcode)
        if self.unavailable:
            raise PosUnavailable("offline")
        return {"barcode": barcode, "product": self.product}

    def apply(self, command):
        self.applied.append(command)
        return {"ok": True}


class VisionClientContractTests(unittest.TestCase):
    def test_google_client_uses_a_bounded_structured_response_without_a_real_api_call(self):
        captured = {}

        class FakePart:
            @staticmethod
            def from_bytes(*, data, mime_type):
                return {"bytes": data, "mime_type": mime_type}

        class FakeModels:
            def generate_content(self, *, model, contents, config):
                captured.update(model=model, contents=contents, config=config)
                return types.SimpleNamespace(parsed=None, text=json.dumps({
                    "same_product": True,
                    "suggested_name_th": "น้ำผลไม้ทดสอบ",
                    "brand": "",
                    "product_type": "น้ำผลไม้",
                    "variant": "",
                    "size": "",
                    "confidence": 0.8,
                    "warnings": [],
                }), usage_metadata=types.SimpleNamespace(
                    prompt_token_count=800,
                    candidates_token_count=120,
                    thoughts_token_count=10,
                ))

        class FakeClient:
            def __init__(self, **kwargs):
                captured["client_options"] = kwargs
                self.models = FakeModels()

        fake_genai = types.ModuleType("google.genai")
        fake_genai.Client = FakeClient
        fake_genai.types = types.SimpleNamespace(Part=FakePart)
        fake_google = types.ModuleType("google")
        fake_google.genai = fake_genai
        with patch.dict(sys.modules, {"google": fake_google, "google.genai": fake_genai}):
            result = GoogleProductVisionClient("test-key", "gemini-3.5-flash").analyze_product(
                [png_bytes("red"), png_bytes("blue")]
            )

        self.assertTrue(result.same_product)
        self.assertEqual((result.usage.prompt_tokens, result.usage.candidate_tokens, result.usage.thought_tokens), (800, 120, 10))
        self.assertEqual(captured["config"]["max_output_tokens"], MAX_GEMINI_RESPONSE_TOKENS)
        self.assertEqual(captured["config"]["thinking_config"], {"thinking_budget": 0})
        self.assertNotIn("response_mime_type", captured["config"])
        self.assertNotIn("response_json_schema", captured["config"])
        self.assertIn("same_product", captured["contents"][0])
        self.assertEqual(len(captured["contents"]), 3)


class VisionWorkflowTests(unittest.TestCase):
    group_id = "C-vision"
    user_id = "U-owner"

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.store = BotStore(Path(self.temp.name))
        self.line = FakeLine()
        self.decoder = FakeDecoder()
        self.vision = FakeVision()
        self.pos = FakePos()
        self.workflow = BotWorkflow(
            self.store,
            self.line,
            self.pos,
            self.decoder,
            vision_client=self.vision,
            vision_group_ids=frozenset({self.group_id}),
            gemini_max_attempts=2,
            retry_seconds=1,
        )
        self.front = png_bytes("red")
        self.back = png_bytes("blue")
        self.line.contents = {"front": self.front, "back": self.back}
        self.decoder.results = {self.front: {"VISION-001"}, self.back: {"VISION-001"}}

    def tearDown(self):
        self.temp.cleanup()

    def image_event(self, message_id, index=None, total=2, *, group_id=None, user_id=None, set_id="set-1"):
        message = {"type": "image", "id": message_id}
        if index is not None:
            message["imageSet"] = {"id": set_id, "index": index, "total": total}
        return {
            "type": "message",
            "replyToken": f"reply-{message_id}",
            "source": {"type": "group", "groupId": group_id or self.group_id, "userId": user_id or self.user_id},
            "message": message,
        }

    def text_event(self, text, *, user_id=None):
        return {
            "type": "message",
            "replyToken": f"reply-text-{text}",
            "source": {"type": "group", "groupId": self.group_id, "userId": user_id or self.user_id},
            "message": {"type": "text", "id": f"text-{text}", "text": text},
        }

    def collect_pair(self, *, reverse=False, image_set=True, set_id="set-1"):
        first = self.image_event("front", 1 if image_set else None, set_id=set_id)
        second = self.image_event("back", 2 if image_set else None, set_id=set_id)
        for event in (second, first) if reverse else (first, second):
            self.workflow.handle_event(event)
        with self.store.session() as db:
            return db.execute("SELECT * FROM vision_jobs").fetchone()

    def process_pair(self):
        self.workflow.process_due_vision_jobs()
        return self.store.conversation(self.group_id, self.user_id)

    def test_imageset_is_order_independent_deduplicates_barcode_and_calls_gemini_once(self):
        job = self.collect_pair(reverse=True)
        self.assertEqual(job["status"], "pending")
        conversation = self.process_pair()
        self.assertEqual(len(self.vision.calls), 1)
        self.assertEqual(len(self.pos.lookups), 1)
        self.assertEqual(conversation["state"], "VISION_NAME_REVIEW")
        self.assertEqual(self.line.button_reply_tokens[-1], "reply-front")
        self.assertIn("ชื่อที่ระบบเสนอ", self.line.buttons[-1][1])

    def test_fallback_collection_without_imageset_is_owner_scoped_and_uses_fifteen_second_window(self):
        job = self.collect_pair(image_set=False)
        self.assertEqual(job["status"], "pending")
        self.process_pair()
        self.assertEqual(self.store.conversation(self.group_id, self.user_id)["state"], "VISION_NAME_REVIEW")

    def test_images_from_other_user_or_group_never_mix(self):
        self.workflow.vision_group_ids = frozenset({self.group_id, "C-other"})
        self.workflow.handle_event(self.image_event("front", 1, user_id="U-a", set_id="a"))
        self.workflow.handle_event(self.image_event("back", 2, user_id="U-b", set_id="a"))
        self.workflow.handle_event(self.image_event("back", 2, group_id="C-other", set_id="a"))
        with self.store.session() as db:
            rows = db.execute("SELECT group_id,user_id,status FROM vision_jobs ORDER BY group_id,user_id").fetchall()
        self.assertEqual([(row["group_id"], row["user_id"], row["status"]) for row in rows], [
            ("C-other", self.user_id, "collecting"),
            (self.group_id, "U-a", "collecting"),
            (self.group_id, "U-b", "collecting"),
        ])

    def test_total_other_than_two_is_rejected_without_job(self):
        self.workflow.handle_event(self.image_event("front", 1, total=1))
        self.assertIn("ครั้งละ 2 รูป", self.line.replies[-1][1])
        with self.store.session() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM vision_jobs").fetchone()[0], 0)

    def test_active_flow_is_not_overwritten_by_more_images(self):
        self.collect_pair()
        self.process_pair()
        self.workflow.handle_event(self.image_event("front", 1, set_id="later"))
        self.assertEqual(self.store.conversation(self.group_id, self.user_id)["state"], "VISION_NAME_REVIEW")
        with self.store.session() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM vision_jobs").fetchone()[0], 1)

    def test_second_imageset_does_not_displace_an_incomplete_owner_collection(self):
        self.workflow.handle_event(self.image_event("front", 1, set_id="first-set"))
        self.workflow.handle_event(self.image_event("other-front", 1, set_id="second-set"))
        with self.store.session() as db:
            row = db.execute(
                "SELECT job_id,image_set_id,image_message_ids_json,status FROM vision_jobs"
            ).fetchone()
        self.assertEqual(row["image_set_id"], "imageset:first-set")
        self.assertEqual(json.loads(row["image_message_ids_json"]), {"1": "front"})
        self.assertEqual(row["status"], "collecting")

        self.workflow.handle_event(self.image_event("back", 2, set_id="first-set"))
        self.assertEqual(self.store.vision_job(row["job_id"])["status"], "pending")

    def test_no_barcode_skips_gemini_and_pos_create(self):
        self.decoder.results = {self.front: set(), self.back: set()}
        self.collect_pair()
        self.process_pair()
        self.assertEqual(self.vision.calls, [])
        self.assertEqual(self.pos.lookups, [])
        self.assertEqual(self.pos.applied, [])
        self.assertIn("อ่านบาร์โค้ด", self.line.replies[-1][1])

    def test_multiple_distinct_barcodes_are_rejected_before_lookup_or_gemini(self):
        self.decoder.results = {self.front: {"A"}, self.back: {"B"}}
        self.collect_pair()
        self.process_pair()
        self.assertEqual(self.vision.calls, [])
        self.assertEqual(self.pos.lookups, [])
        self.assertIn("มากกว่าหนึ่ง", self.line.replies[-1][1])

    def test_existing_named_product_skips_gemini_and_preserves_cost_when_only_sale_changes(self):
        self.pos.product = {
            "product_uuid": "existing-uuid", "revision": "revision-1", "name_th": "สินค้าเดิม",
            "cost_satang": 1250, "sale_baht": 20, "is_placeholder": False,
        }
        self.collect_pair()
        conversation = self.process_pair()
        self.assertEqual(self.vision.calls, [])
        self.assertEqual(conversation["state"], "VISION_EXISTING_SALE_REVIEW")
        self.workflow.handle_event(self.text_event("แก้ราคาขาย"))
        self.workflow.handle_event(self.text_event("35"))
        self.workflow.handle_event(self.text_event("ยืนยัน"))
        self.assertEqual(self.pos.applied[0]["operation"], "update_prices")
        self.assertEqual(self.pos.applied[0]["cost_satang"], 1250)
        self.assertEqual(self.pos.applied[0]["sale_baht"], 35)

    def test_placeholder_calls_gemini_then_creates_with_zero_cost_uuid_revision_and_no_image(self):
        self.pos.product = {
            "product_uuid": "placeholder-uuid", "revision": "revision-2", "name_th": "สินค้าไม่ทราบชื่อ (VISION-001)",
            "cost_satang": 0, "sale_baht": 0, "is_placeholder": True,
        }
        self.collect_pair()
        self.process_pair()
        self.assertEqual(len(self.vision.calls), 1)
        self.workflow.handle_event(self.text_event("ใช้ชื่อนี้"))
        self.workflow.handle_event(self.text_event("25"))
        self.workflow.handle_event(self.text_event("ยืนยัน"))
        command = self.pos.applied[0]
        self.assertEqual(command["operation"], "create_or_complete")
        self.assertEqual(command["cost_satang"], 0)
        self.assertEqual(command["sale_baht"], 25)
        self.assertEqual(command["product_uuid"], "placeholder-uuid")
        self.assertEqual(command["expected_revision"], "revision-2")
        self.assertNotIn("image", command)

    def test_manual_name_edit_and_sale_validation_are_owner_bound(self):
        self.collect_pair()
        self.process_pair()
        self.workflow.handle_event(self.text_event("แก้ไขชื่อ"))
        self.workflow.handle_event(self.text_event("ชื่อของสมาชิกอื่น", user_id="U-other"))
        self.assertEqual(self.store.conversation(self.group_id, self.user_id)["state"], "VISION_NAME_EDIT")
        self.workflow.handle_event(self.text_event("  ชื่อ   ที่ถูกต้อง  "))
        self.assertEqual(self.store.conversation(self.group_id, self.user_id)["data"]["name_th"], "ชื่อ ที่ถูกต้อง")
        for invalid in ("0", "-1", "12.50", "abc"):
            self.workflow.handle_event(self.text_event(invalid))
            self.assertEqual(self.store.conversation(self.group_id, self.user_id)["state"], "VISION_WAIT_SALE_PRICE")
        self.workflow.handle_event(self.text_event("45"))
        self.workflow.handle_event(self.text_event("แก้ราคา"))
        self.workflow.handle_event(self.text_event("50"))
        self.workflow.handle_event(self.text_event("ยืนยัน"))
        self.assertEqual(self.pos.applied[0]["name_th"], "ชื่อ ที่ถูกต้อง")
        self.assertEqual(self.pos.applied[0]["sale_baht"], 50)
        self.assertEqual(self.pos.applied[0]["cost_satang"], 0)

    def test_retryable_gemini_failure_retries_once_then_falls_back_to_manual_name(self):
        self.vision.error = VisionRetryableError("429")
        self.collect_pair()
        self.process_pair()
        with self.store.session() as db:
            row = db.execute("SELECT status,attempts FROM vision_jobs").fetchone()
            self.assertEqual((row["status"], row["attempts"]), ("retry_wait", 1))
            db.execute("UPDATE vision_jobs SET next_attempt_at=?", (iso_now(),))
        self.process_pair()
        self.assertEqual(len(self.vision.calls), 2)
        self.assertEqual(self.store.conversation(self.group_id, self.user_id)["state"], "VISION_NAME_EDIT")

    def test_monthly_budget_blocks_gemini_before_provider_call_and_uses_manual_flow(self):
        self.workflow.gemini_monthly_budget_microusd = 100
        self.collect_pair()
        self.process_pair()
        self.assertEqual(self.vision.calls, [])
        self.assertEqual(self.store.conversation(self.group_id, self.user_id)["state"], "VISION_NAME_EDIT")
        self.assertIn("วงเงิน AI", self.line.replies[-1][1])
        diagnostics = self.store.gemini_budget_diagnostics(100)
        self.assertEqual(diagnostics["request_count"], 0)
        self.assertEqual(diagnostics["remaining_budget_usd"], "0.000100")

    def test_actual_provider_usage_replaces_conservative_reservation(self):
        result = self.vision.result
        self.vision.result = ProductVisionResult(
            same_product=result.same_product,
            suggested_name_th=result.suggested_name_th,
            brand=result.brand,
            product_type=result.product_type,
            variant=result.variant,
            size=result.size,
            confidence=result.confidence,
            warnings=result.warnings,
            usage=GeminiUsage(prompt_tokens=1_000, candidate_tokens=100),
        )
        self.collect_pair()
        self.process_pair()
        diagnostics = self.store.gemini_budget_diagnostics(1_000_000)
        self.assertEqual(diagnostics["request_count"], 1)
        self.assertEqual(diagnostics["estimated_cost_usd"], "0.000400")
        self.assertEqual(diagnostics["actual_cost_usd"], "0.000400")

    def test_invalid_gemini_response_uses_manual_name_and_same_product_false_requires_new_images(self):
        self.vision.error = VisionError("invalid json")
        self.collect_pair()
        self.process_pair()
        self.assertEqual(self.store.conversation(self.group_id, self.user_id)["state"], "VISION_NAME_EDIT")
        self.store.close_flow(self.group_id, self.user_id)
        self.vision.error = None
        self.vision.result = ProductVisionResult(False, "", "", "", "", "", 0.0, ("different",))
        self.collect_pair(image_set=True, set_id="set-2")
        self.process_pair()
        self.assertIsNone(self.store.conversation(self.group_id, self.user_id))
        self.assertIn("คนละสินค้า", self.line.replies[-1][1])

    def test_jobs_store_only_message_ids_and_recover_processing_after_restart(self):
        job = self.collect_pair()
        job_id = job["job_id"]
        with self.store.session() as db:
            db.execute("UPDATE vision_jobs SET status='processing',updated_at='2000-01-01T00:00:00+00:00'")
            persisted = db.execute("SELECT image_message_ids_json FROM vision_jobs WHERE job_id=?", (job_id,)).fetchone()[0]
        self.assertNotIn(self.front.hex(), persisted)
        recovered = BotStore(Path(self.temp.name)).claim_due_vision_jobs()
        self.assertEqual(recovered[0]["job_id"], job_id)
        self.assertEqual(recovered[0]["image_message_ids"], {"1": "front", "2": "back"})
        self.assertEqual(list(Path(self.temp.name).glob("*.png")), [])

    def test_vision_worker_claims_one_job_at_a_time(self):
        self.collect_pair()
        self.workflow.handle_event(self.image_event("front", 1, user_id="U-second", set_id="second"))
        self.workflow.handle_event(self.image_event("back", 2, user_id="U-second", set_id="second"))
        worker = VisionWorker(self.workflow, self.store)
        worker.process_once()
        with self.store.session() as db:
            completed = db.execute("SELECT COUNT(*) FROM vision_jobs WHERE status='completed'").fetchone()[0]
            pending = db.execute("SELECT COUNT(*) FROM vision_jobs WHERE status='pending'").fetchone()[0]
        self.assertEqual((completed, pending), (1, 1))


class VisionWebhookAndConfigurationTests(unittest.TestCase):
    def settings(self, root, **overrides):
        values = {
            "channel_secret": "line-channel-secret-for-tests",
            "channel_access_token": "line-access-token-for-tests",
            "allowed_group_ids": frozenset({"C-vision", "C-legacy"}),
            "bot_user_id": "U-bot",
            "pos_base_url": "https://pos.example.test",
            "pos_shared_secret": "x" * 32,
            "data_root": Path(root),
            "vision_product_group_ids": frozenset({"C-vision"}),
            "gemini_api_key": "test-gemini-key",
            "gemini_model": "gemini-2.5-flash",
            "gemini_pricing_configured": True,
        }
        values.update(overrides)
        return BotSettings(**values)

    def signed_webhook(self, app, settings, event):
        raw = json.dumps({"events": [event]}).encode("utf-8")
        signature = base64.b64encode(hmac.new(settings.channel_secret.encode(), raw, hashlib.sha256).digest()).decode()
        return app.test_client().post("/webhook", data=raw, content_type="application/json", headers={"X-Line-Signature": signature})

    def test_duplicate_webhook_does_not_create_duplicate_vision_job(self):
        with tempfile.TemporaryDirectory() as temporary:
            line = FakeLine()
            front, back = png_bytes("red"), png_bytes("blue")
            line.contents = {"front": front, "back": back}
            decoder = FakeDecoder()
            decoder.results = {front: {"DUP-1"}, back: {"DUP-1"}}
            settings = self.settings(temporary)
            app = create_app(settings, line_client=line, pos_client=FakePos(), decoder=decoder, vision_client=FakeVision(), start_worker=False)
            event = {
                "webhookEventId": "duplicate-1", "type": "message", "replyToken": "reply-front",
                "source": {"type": "group", "groupId": "C-vision", "userId": "U-owner"},
                "message": {"type": "image", "id": "front", "imageSet": {"id": "set-1", "index": 1, "total": 2}},
            }
            self.assertEqual(self.signed_webhook(app, settings, event).get_json()["accepted"], 1)
            self.assertEqual(self.signed_webhook(app, settings, event).get_json()["accepted"], 0)
            app.extensions["line_bot_worker"].process_once()
            self.assertEqual(self.signed_webhook(app, settings, event | {
                "webhookEventId": "duplicate-2", "replyToken": "reply-back",
                "message": {"type": "image", "id": "back", "imageSet": {"id": "set-1", "index": 2, "total": 2}},
            }).get_json()["accepted"], 1)
            app.extensions["line_bot_worker"].process_once()
            with app.config["BOT_STORE"].session() as db:
                self.assertEqual(db.execute("SELECT COUNT(*) FROM vision_jobs").fetchone()[0], 1)
                self.assertEqual(db.execute("SELECT status FROM vision_jobs").fetchone()[0], "pending")

    def test_config_requires_vision_subset_key_and_model_only_when_vision_enabled(self):
        with tempfile.TemporaryDirectory() as temporary:
            self.settings(temporary).validate()
            self.settings(temporary, vision_product_group_ids=frozenset(), gemini_api_key="", gemini_model="").validate()
            with self.assertRaisesRegex(RuntimeError, "subset"):
                self.settings(temporary, vision_product_group_ids=frozenset({"C-other"})).validate()
            with self.assertRaisesRegex(RuntimeError, "GEMINI_API_KEY"):
                self.settings(temporary, gemini_api_key="").validate()
            with self.assertRaisesRegex(RuntimeError, "GEMINI_MODEL"):
                self.settings(temporary, gemini_model="").validate()
            with self.assertRaisesRegex(RuntimeError, "explicit model pricing"):
                self.settings(temporary, gemini_pricing_configured=False).validate()
            with self.assertRaisesRegex(RuntimeError, "no automatic Gemini retry"):
                self.settings(temporary, gemini_max_attempts=2).validate()

    def test_environment_template_permissions_match_the_dedicated_service_account(self):
        repository = Path(__file__).resolve().parents[1]
        template = (repository / "line_bot" / ".env.example").read_text(encoding="utf-8")
        installer = (repository / "deploy" / "line-bot" / "install-vps.sh").read_text(encoding="utf-8")
        self.assertIn("root:raisanngam-line-bot", template)
        self.assertIn("mode 0640", template)
        self.assertIn("-o root -g raisanngam-line-bot -m 0640", installer)

    def test_legacy_group_continues_to_use_quote_flow(self):
        with tempfile.TemporaryDirectory() as temporary:
            settings = self.settings(temporary)
            line = FakeLine()
            image = png_bytes("green")
            line.contents = {"legacy-image": image}
            decoder = FakeDecoder()
            decoder.results = {image: {"LEGACY-1"}}
            pos = FakePos({
                "product_uuid": "legacy-uuid", "revision": "legacy-r1", "name_th": "สินค้าเดิม",
                "cost_satang": 1000, "sale_baht": 20, "is_placeholder": False,
            })
            workflow = BotWorkflow(
                BotStore(Path(temporary)), line, pos, decoder, vision_client=FakeVision(),
                vision_group_ids=settings.vision_product_group_ids,
            )
            workflow.handle_event({
                "type": "message", "source": {"type": "group", "groupId": "C-legacy", "userId": "U-owner"},
                "message": {"type": "image", "id": "legacy-image"},
            })
            workflow.handle_event({
                "type": "message", "replyToken": "legacy-reply",
                "source": {"type": "group", "groupId": "C-legacy", "userId": "U-owner"},
                "message": {"type": "text", "id": "legacy-quote", "text": "บอท", "quotedMessageId": "legacy-image"},
            })
            self.assertEqual(line.buttons[-1][2], ["แก้ราคาทุน/ราคาขาย"])
            self.assertIn("ราคาทุน : 10.00 บาท", line.buttons[-1][1])
