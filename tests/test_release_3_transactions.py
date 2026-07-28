import queue
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import g

from pos_app import create_app
from pos_app.database import get_db
from pos_app.routes.online import online_settings, validate_cart
from pos_app.services import sales as sales_service
from pos_app.services.online_orders import create_order, expire_pending_orders
from pos_app.services.sales import SaleError, complete_sale, void_sale
from tests.online_helpers import register_customer


class _PauseAfterUnlockedSelect:
    """Pause matching legacy pre-lock reads while remaining transparent to sqlite."""

    def __init__(self, connection, barrier, marker):
        self._connection = connection
        self._barrier = barrier
        self._marker = marker
        self.paused_before_transaction = False

    @property
    def in_transaction(self):
        return self._connection.in_transaction

    def execute(self, sql, parameters=()):
        cursor = self._connection.execute(sql, parameters)
        normalized = " ".join(sql.lower().split())
        if self._marker in normalized and not self._connection.in_transaction:
            self.paused_before_transaction = True
            self._barrier.wait(timeout=5)
        return cursor

    def __getattr__(self, name):
        return getattr(self._connection, name)


class Release3TransactionTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.database_path = str(Path(self.folder.name) / "release-3.db")
        self.app = create_app({
            "TESTING": True,
            "DATABASE": self.database_path,
            "PROJECT_ROOT": self.folder.name,
        })
        with self.app.app_context():
            db = get_db()
            category = db.execute("SELECT id FROM categories LIMIT 1").fetchone()[0]
            unit = db.execute("SELECT id FROM units LIMIT 1").fetchone()[0]
            db.execute("UPDATE settings SET value='0' WHERE key='allow_negative_stock'")
            db.execute("UPDATE settings SET value='0' WHERE key='online_allow_negative_stock'")
            db.execute(
                """INSERT INTO products
                   (barcode,name_th,category_id,unit_id,cost_satang,price_satang,stock_quantity,
                    allow_decimal_quantity,is_online_available)
                   VALUES('R3-UNIT','สินค้าทดสอบพร้อมกัน',?,?,500,1000,1,0,1)""",
                (category, unit),
            )
            db.execute(
                """INSERT INTO products
                   (barcode,name_th,category_id,unit_id,cost_satang,price_satang,stock_quantity,
                    allow_decimal_quantity,is_online_available)
                   VALUES('R3-WEIGHT','สินค้าชั่งน้ำหนัก',?,?,400,1000,10,1,1)""",
                (category, unit),
            )
            db.execute(
                """INSERT INTO delivery_locations(name,delivery_fee_satang,minimum_order_satang,room_required)
                   VALUES('จุดส่งทดสอบ',0,0,0)"""
            )
            db.commit()
            self.unit_uuid = db.execute("SELECT product_uuid FROM products WHERE barcode='R3-UNIT'").fetchone()[0]
            self.weight_uuid = db.execute("SELECT product_uuid FROM products WHERE barcode='R3-WEIGHT'").fetchone()[0]

    def tearDown(self):
        self.folder.cleanup()

    def _cash_payload(self, product_uuid, quantity):
        return {
            "items": [{"product_uuid": product_uuid, "quantity": quantity}],
            "payment_method": "cash",
            "amount_received_satang": 100000,
        }

    def _run_threads(self, workers):
        threads = [threading.Thread(target=worker, daemon=True) for worker in workers]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
        self.assertFalse(any(thread.is_alive() for thread in threads), "concurrency test thread did not finish")

    def _prepare_online_customer(self):
        client = self.app.test_client()
        register_customer(client)
        with self.app.app_context():
            db = get_db()
            customer_id = db.execute("SELECT id FROM customers ORDER BY id DESC LIMIT 1").fetchone()[0]
            db.execute("UPDATE settings SET value='1' WHERE key='online_ordering_enabled'")
            db.execute("UPDATE products SET stock_quantity=5 WHERE product_uuid=?", (self.unit_uuid,))
            db.commit()
        return customer_id

    def _online_payload(self, key):
        return {
            "items": [{"product_uuid": self.unit_uuid, "quantity": 1}],
            "delivery_location_id": 1,
            "room_reference": "",
            "payment_method": "cash",
            "contact_phone": "0812345678",
            "contact_name": "ลูกค้าทดสอบ",
            "idempotency_key": key,
        }

    def _create_online_order(self, customer_id, key):
        with self.app.test_request_context("/order/api/orders", method="POST"):
            db = get_db()
            location = db.execute("SELECT * FROM delivery_locations WHERE id=1").fetchone()
            return create_order(
                customer_id,
                self._online_payload(key),
                validate_cart,
                online_settings(),
                location,
            )

    def test_checkout_locks_before_authoritative_cart_validation(self):
        start = threading.Barrier(2)
        legacy_read_barrier = threading.Barrier(2)
        results = queue.Queue()
        transaction_flags = []
        original_calculate_cart = sales_service.calculate_cart

        def synchronized_calculate_cart(*args, **kwargs):
            cart = original_calculate_cart(*args, **kwargs)
            in_transaction = get_db().in_transaction
            transaction_flags.append(in_transaction)
            if not in_transaction:
                legacy_read_barrier.wait(timeout=5)
            return cart

        def worker():
            with self.app.app_context():
                start.wait(timeout=5)
                try:
                    results.put(("ok", complete_sale(self._cash_payload(self.unit_uuid, 1), 1)[0]))
                except Exception as exc:  # The losing checkout must return a domain error.
                    results.put(("error", exc))

        with patch("pos_app.services.sales.calculate_cart", side_effect=synchronized_calculate_cart):
            self._run_threads([worker, worker])

        outcomes = [results.get_nowait(), results.get_nowait()]
        self.assertEqual(sum(status == "ok" for status, _ in outcomes), 1)
        errors = [value for status, value in outcomes if status == "error"]
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], SaleError)
        self.assertTrue(transaction_flags)
        self.assertTrue(all(transaction_flags))
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.execute("SELECT COUNT(*) FROM sales").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT stock_quantity FROM products WHERE product_uuid=?", (self.unit_uuid,)).fetchone()[0], 0)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM stock_movements WHERE movement_type='sale'").fetchone()[0], 1)

    def test_concurrent_voids_cannot_over_refund_or_over_restock(self):
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE products SET stock_quantity=2 WHERE product_uuid=?", (self.unit_uuid,))
            db.commit()
            sale_id = complete_sale(self._cash_payload(self.unit_uuid, 2), 1)[0]
            item_id = db.execute("SELECT id FROM sale_items WHERE sale_id=?", (sale_id,)).fetchone()[0]

        start = threading.Barrier(2)
        legacy_read_barrier = threading.Barrier(2)
        results = queue.Queue()

        def worker():
            with self.app.app_context():
                real_connection = get_db()
                proxy = _PauseAfterUnlockedSelect(real_connection, legacy_read_barrier, "from sale_items")
                g.db = proxy
                start.wait(timeout=5)
                try:
                    result = void_sale(
                        sale_id,
                        {"void_type": "partial", "reason": "ทดสอบพร้อมกัน", "items": [
                            {"sale_item_id": item_id, "quantity": 2},
                        ]},
                        1,
                    )
                    results.put(("ok", result, proxy.paused_before_transaction))
                except Exception as exc:
                    results.put(("error", exc, proxy.paused_before_transaction))

        self._run_threads([worker, worker])
        outcomes = [results.get_nowait(), results.get_nowait()]
        self.assertEqual(sum(status == "ok" for status, _, _ in outcomes), 1)
        errors = [value for status, value, _ in outcomes if status == "error"]
        self.assertEqual(len(errors), 1)
        self.assertIsInstance(errors[0], SaleError)
        self.assertFalse(any(paused for _, _, paused in outcomes))
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.execute("SELECT status FROM sales WHERE id=?", (sale_id,)).fetchone()[0], "voided")
            self.assertEqual(db.execute("SELECT voided_quantity FROM sale_items WHERE id=?", (item_id,)).fetchone()[0], 2)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM sale_voids WHERE sale_id=?", (sale_id,)).fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT stock_quantity FROM products WHERE product_uuid=?", (self.unit_uuid,)).fetchone()[0], 2)

    def test_weighted_sale_supports_partial_and_full_decimal_void(self):
        with self.app.app_context():
            db = get_db()
            sale_id = complete_sale(self._cash_payload(self.weight_uuid, 0.5), 1)[0]
            item_id = db.execute("SELECT id FROM sale_items WHERE sale_id=?", (sale_id,)).fetchone()[0]
            partial_id, partial_refund = void_sale(
                sale_id,
                {"void_type": "partial", "reason": "คืนบางส่วน", "items": [
                    {"sale_item_id": item_id, "quantity": 0.25},
                ]},
                1,
            )
            self.assertGreater(partial_id, 0)
            self.assertEqual(partial_refund, 250)
            self.assertAlmostEqual(db.execute(
                "SELECT stock_quantity FROM products WHERE product_uuid=?", (self.weight_uuid,)
            ).fetchone()[0], 9.75)
            void_sale(sale_id, {"void_type": "full", "reason": "คืนส่วนที่เหลือ"}, 1)
            self.assertAlmostEqual(db.execute("SELECT voided_quantity FROM sale_items WHERE id=?", (item_id,)).fetchone()[0], 0.5)
            self.assertAlmostEqual(db.execute(
                "SELECT stock_quantity FROM products WHERE product_uuid=?", (self.weight_uuid,)
            ).fetchone()[0], 10)
            self.assertEqual(db.execute("SELECT status FROM sales WHERE id=?", (sale_id,)).fetchone()[0], "voided")

    def test_concurrent_idempotent_submissions_return_one_order(self):
        customer_id = self._prepare_online_customer()
        start = threading.Barrier(2)
        legacy_read_barrier = threading.Barrier(2)
        results = queue.Queue()

        def worker():
            with self.app.test_request_context("/order/api/orders", method="POST"):
                real_connection = get_db()
                proxy = _PauseAfterUnlockedSelect(
                    real_connection,
                    legacy_read_barrier,
                    "select public_id,order_number from online_orders where customer_id",
                )
                g.db = proxy
                location = proxy.execute("SELECT * FROM delivery_locations WHERE id=1").fetchone()
                settings = dict(proxy.execute("SELECT key,value FROM settings").fetchall())
                start.wait(timeout=5)
                try:
                    order, duplicate = create_order(
                        customer_id,
                        self._online_payload("concurrent-order-key-123"),
                        validate_cart,
                        settings,
                        location,
                    )
                    results.put(("ok", order["public_id"], duplicate, proxy.paused_before_transaction))
                except Exception as exc:
                    results.put(("error", exc, False, proxy.paused_before_transaction))

        self._run_threads([worker, worker])
        outcomes = [results.get_nowait(), results.get_nowait()]
        self.assertTrue(all(status == "ok" for status, *_ in outcomes))
        self.assertEqual(len({public_id for _, public_id, _, _ in outcomes}), 1)
        self.assertEqual(sorted(duplicate for _, _, duplicate, _ in outcomes), [False, True])
        self.assertFalse(any(paused for *_, paused in outcomes))
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.execute("SELECT COUNT(*) FROM online_orders").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM stock_reservations").fetchone()[0], 1)
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM audit_logs WHERE action='online_order_submitted'"
            ).fetchone()[0], 1)

    def test_expiry_selects_and_transitions_under_one_write_lock(self):
        customer_id = self._prepare_online_customer()
        self._create_online_order(customer_id, "expiry-lock-key-12345")
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE online_orders SET expires_at='2000-01-01T00:00:00+00:00'")
            db.commit()
        with self.app.test_request_context("/order"):
            real_connection = get_db()
            proxy = _PauseAfterUnlockedSelect(
                real_connection,
                threading.Barrier(1),
                "select id,status from online_orders",
            )
            g.db = proxy
            self.assertEqual(expire_pending_orders(), 1)
            self.assertFalse(proxy.paused_before_transaction)
        with self.app.app_context():
            db = get_db()
            self.assertEqual(db.execute("SELECT status FROM online_orders").fetchone()[0], "expired")
            self.assertEqual(db.execute("SELECT status FROM stock_reservations").fetchone()[0], "released")
            self.assertEqual(db.execute(
                "SELECT COUNT(*) FROM online_order_status_history WHERE new_status='expired'"
            ).fetchone()[0], 1)

    def test_expiry_and_staff_transition_have_one_consistent_winner(self):
        customer_id = self._prepare_online_customer()
        self._create_online_order(customer_id, "expiry-race-key-12345")
        with self.app.app_context():
            db = get_db()
            db.execute("UPDATE online_orders SET expires_at='2000-01-01T00:00:00+00:00'")
            db.commit()

        start = threading.Barrier(2)
        results = queue.Queue()

        def expire_worker():
            with self.app.test_request_context("/order"):
                start.wait(timeout=5)
                results.put(("expired", expire_pending_orders()))

        def transition_worker():
            with self.app.app_context():
                db = get_db()
                start.wait(timeout=5)
                db.execute("BEGIN IMMEDIATE")
                updated = db.execute(
                    """UPDATE online_orders SET status='preparing',updated_at=CURRENT_TIMESTAMP
                       WHERE id=1 AND status IN ('submitted','accepted')"""
                ).rowcount
                db.commit()
                results.put(("preparing", updated))

        self._run_threads([expire_worker, transition_worker])
        outcome = dict([results.get_nowait(), results.get_nowait()])
        with self.app.app_context():
            db = get_db()
            status = db.execute("SELECT status FROM online_orders WHERE id=1").fetchone()[0]
            reservation_status = db.execute("SELECT status FROM stock_reservations WHERE order_id=1").fetchone()[0]
        if outcome["preparing"] == 1:
            self.assertEqual(outcome["expired"], 0)
            self.assertEqual((status, reservation_status), ("preparing", "active"))
        else:
            self.assertEqual(outcome["expired"], 1)
            self.assertEqual((status, reservation_status), ("expired", "released"))

    def test_fresh_schema_contains_voided_quantity(self):
        with self.app.app_context():
            columns = {row[1] for row in get_db().execute("PRAGMA table_info(sale_items)").fetchall()}
        self.assertIn("voided_quantity", columns)


if __name__ == "__main__":
    unittest.main()
