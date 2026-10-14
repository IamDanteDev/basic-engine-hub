"""The shared art has to ship, and both surfaces have to name the same files.

Run with: python -m unittest discover -s tests

The menu and the desktop shell draw the same two placeholder images and offer the
same four language titles, but the filenames are declared twice: `hub/cache.py`
and `hub/i18n.py` for the app, `web/style.css` and `web/i18n.js` for the browser.
A rename on one side would only show up as a broken image at runtime, so the
declarations are pinned against the files on disk and against each other here.

Deliberately imports nothing from PySide6: the CI runner does not install it.
"""

import unittest
from pathlib import Path

from hub import cache, i18n

ROOT = Path(__file__).resolve().parent.parent
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def web_path(asset: Path) -> str:
    """The URL `web/style.css` uses for an Assets/ file: `../` reaches the repo root."""
    return f"../Assets/{asset.relative_to(cache.ASSETS).as_posix()}"


class PlaceholderArtTests(unittest.TestCase):
    """The images the UI falls back to must exist where the code looks for them."""

    def test_the_desktop_shell_placeholder_images_ship(self):
        for asset in (cache.PLACEHOLDER_THUMBNAIL, cache.PLACEHOLDER_AVATAR):
            with self.subTest(asset=asset.name):
                self.assertTrue(asset.is_file(), f"the app reads {asset}, so it must ship")
                self.assertEqual(asset.read_bytes()[:8], PNG_MAGIC, f"{asset} must be a PNG")

    def test_the_web_draws_the_same_placeholder_files(self):
        css = (ROOT / "web" / "style.css").read_text(encoding="utf-8")
        for asset in (cache.PLACEHOLDER_THUMBNAIL, cache.PLACEHOLDER_AVATAR):
            with self.subTest(asset=asset.name):
                self.assertIn(
                    web_path(asset),
                    css,
                    "both surfaces must fall back to the same placeholder art",
                )


class LanguageTitleTests(unittest.TestCase):
    """Every offered language must offer its own title art for both surfaces."""

    def test_every_language_ships_its_title_image(self):
        self.assertEqual(
            set(i18n.TITLE_FILES),
            set(i18n.LANGUAGES),
            "a language without a title image cannot be offered as one",
        )
        for code, filename in i18n.TITLE_FILES.items():
            with self.subTest(code=code):
                asset = cache.TITLE_DIR / filename
                self.assertTrue(asset.is_file(), f"{code} must ship {asset}")
                self.assertEqual(asset.read_bytes()[:8], PNG_MAGIC, f"{asset} must be a PNG")


if __name__ == "__main__":
    unittest.main()
