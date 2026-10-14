"""Tests for the desktop shell translations (hub/i18n.py).

Run with: python -m unittest discover -s tests

Deliberately imports nothing from hub.gui: the CI runner installs requests and
beautifulsoup4 but not PySide6, so a test that pulled the widgets in would fail
the build it is supposed to protect.

The `es` values are the verbatim baseline of the copy the app shipped with, so a
handful of the strings that carry real behaviour (the status bar, the counted
labels, the edit prompts with their guillemets) are pinned byte-for-byte.
"""

import unittest

from hub import i18n, settings


def placeholders(value):
    """Return the {placeholder} names a catalog value declares."""
    import re

    return set(re.findall(r"\{(\w+)\}", value))


class LanguageCatalogTests(unittest.TestCase):
    def test_the_four_languages_are_declared_in_order_with_their_own_name(self):
        self.assertEqual(list(i18n.LANGUAGES), ["es", "fr", "pt", "en"])
        self.assertEqual(i18n.LANGUAGES["es"], "Español")
        self.assertEqual(i18n.LANGUAGES["fr"], "Français")
        self.assertEqual(i18n.LANGUAGES["pt"], "Português")
        self.assertEqual(i18n.LANGUAGES["en"], "English")

    def test_every_language_carries_a_full_table(self):
        reference = set(i18n.STRINGS["es"])
        self.assertGreater(len(reference), 60, "the Spanish table is the full inventory")
        self.assertEqual(
            set(i18n.STRINGS),
            set(i18n.LANGUAGES),
            "the offered languages and the tables must be the same set, so a missing table cannot pass unnoticed",
        )
        for code, table in i18n.STRINGS.items():
            self.assertEqual(
                set(table),
                reference,
                f"the {code} table must cover exactly the same keys as the Spanish baseline",
            )
            for key, value in table.items():
                self.assertIsInstance(value, str, f"{code}.{key} must be a string")
                self.assertTrue(value, f"{code}.{key} must not be empty")

    def test_every_table_declares_the_same_placeholders_as_the_baseline(self):
        reference = i18n.STRINGS["es"]
        for code, table in i18n.STRINGS.items():
            for key, value in table.items():
                self.assertEqual(
                    placeholders(value),
                    placeholders(reference[key]),
                    f"{code}.{key} must declare exactly the placeholders the Spanish baseline declares",
                )

    def test_each_language_is_translated_not_a_copy_of_the_baseline(self):
        # A coarse guard, not a translation review: it catches the easy mistake
        # of shipping a language table copied from Spanish. Cognates ("Clones",
        # "Variables") are legitimately identical, hence the lenient threshold.
        reference = i18n.STRINGS["es"]
        for code, table in i18n.STRINGS.items():
            if code == "es":
                continue
            translated = sum(1 for key, value in table.items() if value != reference[key])
            self.assertGreaterEqual(
                translated,
                len(reference) * 0.6,
                f"the {code} table only differs from the Spanish baseline in {translated}/{len(reference)} keys",
            )


class BaselineWordingTests(unittest.TestCase):
    """The Spanish values are the copy the app shipped with: they must not drift."""

    def test_status_bar_wording_is_pinned(self):
        es = i18n.STRINGS["es"]
        self.assertEqual(es["status_ready"], "Listo.")
        self.assertEqual(es["status_load_error"], "No se pudieron cargar los proyectos.")
        self.assertEqual(es["projects_found"], "{total} proyectos encontrados.")
        self.assertEqual(es["filter_count"], "{visible} de {total} proyectos.")

    def test_edit_prompts_keep_their_guillemets(self):
        self.assertEqual(
            i18n.STRINGS["es"]["edit_list_prompt"],
            "Nuevos elementos separados por coma o JSON para «{name}»:",
        )
        self.assertEqual(
            i18n.STRINGS["es"]["edit_value_prompt"], "Nuevo valor para «{name}»:"
        )

    def test_symbol_prefixed_labels_keep_their_symbol(self):
        es = i18n.STRINGS["es"]
        self.assertTrue(es["refresh"].startswith("↻ "))
        self.assertTrue(es["back"].startswith("← "))
        self.assertTrue(es["featured_badge"].startswith("★ "))
        self.assertTrue(es["favorite_add"].startswith("❤ "))
        for code, table in i18n.STRINGS.items():
            self.assertTrue(
                table["refresh"].startswith("↻ "),
                f"{code}.refresh must keep the refresh symbol",
            )
            self.assertTrue(
                table["back"].startswith("← "),
                f"{code}.back must keep the back arrow",
            )


class LanguageSwitchTests(unittest.TestCase):
    def tearDown(self):
        i18n.set_language(i18n.DEFAULT)

    def test_the_default_language_is_english_on_both_sides(self):
        self.assertEqual(i18n.DEFAULT, "en")
        self.assertEqual(
            settings.DEFAULTS["language"],
            i18n.DEFAULT,
            "the persisted default and the catalog default must agree, or a fresh install shows one language and stores another",
        )

    def test_set_language_accepts_the_four_and_falls_back_on_unknown(self):
        for code in i18n.LANGUAGES:
            i18n.set_language(code)
            self.assertEqual(i18n.current(), code)
        i18n.set_language("de")
        self.assertEqual(i18n.current(), "en", "an unknown code falls back to the default")

    def test_tr_renders_each_language_and_falls_back_es_then_key(self):
        i18n.set_language("fr")
        self.assertEqual(i18n.tr("back"), "← Retour au menu")
        i18n.set_language("pt")
        self.assertEqual(i18n.tr("back"), "← Voltar ao menu")
        i18n.set_language("en")
        self.assertEqual(i18n.tr("back"), "← Back to menu")
        i18n.set_language("es")
        self.assertEqual(i18n.tr("back"), "← Volver al menú")

    def test_tr_formats_placeholders_in_every_language(self):
        for code in i18n.LANGUAGES:
            i18n.set_language(code)
            rendered = i18n.tr("filter_count", visible=3, total=9)
            self.assertIn("3", rendered)
            self.assertIn("9", rendered)
            self.assertNotIn("{", rendered, f"{code} must leave no placeholder behind")

    def test_tr_returns_the_key_when_no_table_carries_it(self):
        self.assertEqual(i18n.tr("no_such_key"), "no_such_key")


if __name__ == "__main__":
    unittest.main()
