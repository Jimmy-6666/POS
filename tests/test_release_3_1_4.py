import unittest
from pathlib import Path

from pos_app.runtime_paths import DEFAULT_APP_VERSION


ROOT = Path(__file__).resolve().parent.parent


class Release314Tests(unittest.TestCase):
    def test_pos_cart_scroll_and_non_action_focus_are_wired(self):
        js = (ROOT / "pos_app" / "static" / "js" / "pos.js").read_text(
            encoding="utf-8"
        )

        render_start = js.index("function renderCart()")
        render_end = js.index("function updateCash()", render_start)
        render_cart = js[render_start:render_end]
        self.assertIn("const cartItems = $('#cartItems');", render_cart)
        self.assertIn("cartItems.scrollTop = cartItems.scrollHeight;", render_cart)
        self.assertLess(
            render_cart.index("cartItems.innerHTML"),
            render_cart.index("cartItems.scrollTop = cartItems.scrollHeight;"),
        )

        self.assertIn("document.addEventListener('click', (event) => {", js)
        self.assertIn("if (scannerBlocked() || !(event.target instanceof Element)) return;", js)
        self.assertIn(
            "a, button, input, select, textarea, summary, label, dialog,",
            js,
        )
        self.assertIn("if (!action) focusProductLookup();", js)

    def test_release_identity_is_314_and_uat_is_explicit(self):
        self.assertEqual(DEFAULT_APP_VERSION, "3.1.5")
        base = (ROOT / "pos_app" / "templates" / "base.html").read_text(
            encoding="utf-8"
        )
        pos = (ROOT / "pos_app" / "templates" / "pos.html").read_text(
            encoding="utf-8"
        )
        start_uat = (ROOT / "start-uat.bat").read_text(encoding="utf-8")
        launcher = (ROOT / "pos_desktop.py").read_text(encoding="utf-8")
        release_note = (ROOT / "VERSION_3.1.4.md").read_text(encoding="utf-8")

        self.assertIn("R3.1.5", base)
        self.assertIn("filename='js/pos.js',v=38", pos)
        self.assertIn('set "POS_PORT=8001"', start_uat)
        self.assertIn('set "POS_APP_VERSION=3.1.5"', start_uat)
        self.assertIn("3.1.5 UAT", start_uat)
        self.assertIn("POS Desktop Launcher · Version 3.1.5", launcher)
        self.assertIn('messagebox.showerror("POS 3.1.5"', launcher)
        self.assertIn("Production", release_note)
        self.assertIn("deployed to Production", release_note)


if __name__ == "__main__":
    unittest.main()
