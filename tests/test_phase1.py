import sqlite3
import tempfile
import unittest
from pathlib import Path

from pos_app import create_app


class Phase1Tests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.database = Path(self.folder.name) / "test.db"
        self.app = create_app({"TESTING": True, "DATABASE": str(self.database)})

    def tearDown(self):
        self.folder.cleanup()

    def test_home_is_protected_and_health_is_ready(self):
        client = self.app.test_client()
        response = client.get("/")
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login", response.headers["Location"])
        self.assertEqual(client.get("/health").get_json(), {"status": "ok", "database": "ready"})

    def test_thai_starter_data_is_idempotent(self):
        create_app({"TESTING": True, "DATABASE": str(self.database)})
        connection = sqlite3.connect(self.database)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM categories").fetchone()[0], 17)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM units").fetchone()[0], 12)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM adjustment_reasons").fetchone()[0], 7)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM payment_methods").fetchone()[0], 3)
        connection.close()


if __name__ == "__main__":
    unittest.main()
