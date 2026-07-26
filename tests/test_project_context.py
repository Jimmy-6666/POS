import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
FIRST_READ = [
    "AI_CONTEXT.md",
    "PROJECT_MAP.md",
    "FEATURE_STATUS.md",
    "DECISIONS.md",
    "CODING_RULES.md",
    "DESIGN_RULES.md",
]


class ProjectContextContractTests(unittest.TestCase):
    def test_first_read_contract_exists_is_ordered_and_compact(self):
        agent_text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        positions = []
        for filename in FIRST_READ:
            path = ROOT / filename
            self.assertTrue(path.is_file(), filename)
            text = path.read_text(encoding="utf-8").strip()
            self.assertTrue(text, filename)
            self.assertLess(
                len(text.split()),
                800,
                f"{filename} is no longer compact; move detail to a linked document",
            )
            positions.append(agent_text.index(f"`{filename}`"))
        self.assertEqual(positions, sorted(positions))

    def test_contract_preserves_sources_and_maps_all_workflows(self):
        agent_text = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
        self.assertIn("REQUIREMENTS_V1.0.md", agent_text)
        self.assertIn("RELEASE_2.0.md", agent_text)
        self.assertIn("VERSION_2.1.md", agent_text)

        project_map = (ROOT / "PROJECT_MAP.md").read_text(encoding="utf-8")
        required_areas = [
            "pos_app/routes/auth.py",
            "pos_app/routes/products.py",
            "pos_app/routes/pos.py",
            "pos_app/routes/inventory.py",
            "pos_app/routes/stock_count.py",
            "pos_app/routes/reporting.py",
            "pos_app/routes/admin.py",
            "work/makro-pos-import",
            "seed_uat.py",
        ]
        for area in required_areas:
            self.assertIn(area, project_map)

        ignore_text = (ROOT / ".rgignore").read_text(encoding="utf-8")
        for generated in ("runtime/", "uat_runtime/", ".venv/", "outputs/"):
            self.assertIn(generated, ignore_text)
        self.assertNotIn("pos_app/", ignore_text)
        self.assertNotIn("tests/", ignore_text)


if __name__ == "__main__":
    unittest.main()
