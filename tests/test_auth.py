"""Tests for the desktop shell's Scratch sign-in core (hub/auth.py).

Run with: python -m unittest discover -s tests

Deliberately imports nothing from PySide6: the CI runner installs requests and
beautifulsoup4 only, so every rule lives in the core and hub/gui.py owns the
widgets.

The rules pinned here are the same ones web/auth.js pins for the browser: the
percent-encoded base64 redirect (raw base64 corrupts on "+"), the trust check on
the returned redirect, the three documented methods with profile-comment's
username requirement, and the privateCode never being persisted.
"""

import base64
import unittest
import urllib.parse
from unittest import mock

import requests

from hub import auth


class FakeResponse:
    """Minimal requests.Response stand-in: status, ok and json()."""

    def __init__(self, payload=None, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.ok = 200 <= status_code < 300

    def json(self):
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


class FakeSettings:
    """Stands in for hub.settings so no test touches a real settings.json."""

    def __init__(self, values=None):
        self.values = dict(values or {})

    def get(self, key, default=None):
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value


class ServiceContractTests(unittest.TestCase):
    """The service, the auth project and the methods are the shipped ones."""

    def test_the_service_and_project_are_the_ones_the_web_uses(self):
        self.assertEqual(auth.AUTH_API_BASE, "https://auth-api.itinerary.eu.org")
        self.assertEqual(auth.AUTH_PROJECT_ID, 1391621033)
        self.assertEqual(
            auth.AUTH_PROJECT_URL, "https://scratch.mit.edu/projects/1391621033/"
        )

    def test_the_three_documented_methods_are_offered(self):
        self.assertEqual(auth.AUTH_METHODS, ("cloud", "comment", "profile-comment"))

    def test_the_app_sends_the_auth_project_as_its_redirect(self):
        # No callback page exists on the desktop, and the value has to be one
        # the app can still verify when the service echoes it back.
        self.assertEqual(auth.AUTH_REDIRECT, auth.AUTH_PROJECT_URL)
        self.assertTrue(auth.is_trusted_redirect(auth.AUTH_REDIRECT, auth.AUTH_REDIRECT))

    def test_an_unknown_method_is_not_known(self):
        self.assertFalse(auth.is_known_method("email"))
        self.assertTrue(auth.is_known_method("cloud"))


class TokensUrlTests(unittest.TestCase):
    def query(self, url):
        return dict(urllib.parse.parse_qsl(urllib.parse.urlsplit(url).query))

    def test_the_url_carries_the_method_the_project_and_the_redirect(self):
        url = auth.build_tokens_url("https://example.com/app", method="comment")
        parts = urllib.parse.urlsplit(url)
        self.assertEqual(parts.netloc, "auth-api.itinerary.eu.org")
        self.assertEqual(parts.path, "/auth/getTokens")
        query = self.query(url)
        self.assertEqual(query["method"], "comment")
        self.assertEqual(query["authProject"], "1391621033")
        self.assertEqual(
            base64.b64decode(query["redirect"]).decode("utf-8"),
            "https://example.com/app",
        )

    def test_the_base64_redirect_is_percent_encoded_never_raw(self):
        # A "+" in raw base64 decodes as a space and silently corrupts the
        # redirect (evidence L6 in odd/tasks/scratch-auth.md).
        target = "https://example.com/x>>>"
        encoded = auth.encode_redirect(target)
        self.assertIn("+", encoded)
        url = auth.build_tokens_url(target)
        self.assertIn("%2B", url)
        self.assertEqual(
            base64.b64decode(dict(urllib.parse.parse_qsl(url.split("?", 1)[1]))["redirect"]).decode(
                "utf-8"
            ),
            target,
        )

    def test_an_unknown_method_falls_back_to_cloud(self):
        url = auth.build_tokens_url("https://example.com/app", method="email")
        self.assertEqual(
            dict(urllib.parse.parse_qsl(url.split("?", 1)[1]))["method"], "cloud"
        )

    def test_profile_comment_carries_the_username(self):
        url = auth.build_tokens_url(
            "https://example.com/app", method="profile-comment", username=" narutoxd123 "
        )
        query = dict(urllib.parse.parse_qsl(url.split("?", 1)[1]))
        self.assertEqual(query["username"], "narutoxd123")
        self.assertEqual(query["method"], "profile-comment")

    def test_the_other_methods_never_send_a_username(self):
        url = auth.build_tokens_url(
            "https://example.com/app", method="cloud", username="narutoxd123"
        )
        self.assertNotIn("username", dict(urllib.parse.parse_qsl(url.split("?", 1)[1])))

    def test_the_verify_url_percent_encodes_the_private_code(self):
        url = auth.verify_url("a+b/c=", api_base="https://auth.example")
        self.assertEqual(url, "https://auth.example/auth/verifyToken/a%2Bb%2Fc%3D")


class RedirectTrustTests(unittest.TestCase):
    """The anti-phishing rule: absent is accepted, different is refused."""

    def setUp(self):
        self.expected = "https://example.com/app"

    def test_an_absent_redirect_is_trusted(self):
        for value in (None, ""):
            with self.subTest(value=value):
                self.assertTrue(auth.is_trusted_redirect(value, self.expected))

    def test_the_same_redirect_in_plain_or_base64_form_is_trusted(self):
        self.assertTrue(auth.is_trusted_redirect(self.expected, self.expected))
        self.assertTrue(
            auth.is_trusted_redirect(auth.encode_redirect(self.expected), self.expected)
        )

    def test_a_trailing_slash_does_not_change_the_url(self):
        self.assertTrue(
            auth.is_trusted_redirect("https://example.com/app/", self.expected)
        )

    def test_another_origin_is_refused(self):
        self.assertFalse(
            auth.is_trusted_redirect("https://evil.example/app", self.expected)
        )
        self.assertFalse(
            auth.is_trusted_redirect(
                auth.encode_redirect("https://evil.example/app"), self.expected
            )
        )

    def test_a_missing_expected_url_never_trusts_a_returned_one(self):
        self.assertFalse(auth.is_trusted_redirect("https://example.com/app", ""))


class VerifyCodeTests(unittest.TestCase):
    def test_a_pending_code_answers_invalid_instead_of_raising(self):
        with mock.patch.object(
            auth.requests, "get", return_value=FakeResponse(status_code=403)
        ):
            self.assertEqual(
                auth.verify_code("abcd"),
                {"valid": False, "username": None, "redirect": None},
            )

    def test_a_confirmed_code_returns_the_username(self):
        payload = {"valid": True, "username": "narutoxd123", "redirect": None}
        with mock.patch.object(auth.requests, "get", return_value=FakeResponse(payload)):
            self.assertEqual(
                auth.verify_code("abcd"),
                {"valid": True, "username": "narutoxd123", "redirect": None},
            )

    def test_a_valid_flag_without_a_username_is_not_a_session(self):
        payload = {"valid": True, "username": "", "redirect": None}
        with mock.patch.object(auth.requests, "get", return_value=FakeResponse(payload)):
            self.assertFalse(auth.verify_code("abcd")["valid"])

    def test_a_transport_failure_raises_the_auth_error(self):
        with mock.patch.object(
            auth.requests, "get", side_effect=requests.RequestException("boom")
        ):
            with self.assertRaises(auth.AuthError):
                auth.verify_code("abcd")


class TokenRequestTests(unittest.TestCase):
    def test_a_request_without_a_private_code_raises(self):
        with mock.patch.object(auth.requests, "get", return_value=FakeResponse({})):
            with self.assertRaises(auth.AuthError):
                auth.request_tokens("https://example.com/app")

    def test_a_failed_request_raises(self):
        with mock.patch.object(
            auth.requests, "get", return_value=FakeResponse(status_code=500)
        ):
            with self.assertRaises(auth.AuthError):
                auth.request_tokens("https://example.com/app")

    def test_the_tokens_come_back_untouched(self):
        payload = {"publicCode": "AB12", "privateCode": "secret", "method": "cloud"}
        with mock.patch.object(auth.requests, "get", return_value=FakeResponse(payload)):
            tokens = auth.request_tokens("https://example.com/app")
        self.assertEqual(tokens["publicCode"], "AB12")
        self.assertEqual(tokens["privateCode"], "secret")

    def test_profile_comment_without_a_username_is_refused(self):
        with mock.patch.object(auth.requests, "get", return_value=FakeResponse({})):
            with self.assertRaises(auth.AuthError):
                auth.request_tokens("https://example.com/app", method="profile-comment")

    def test_a_transport_failure_raises_the_auth_error(self):
        with mock.patch.object(
            auth.requests, "get", side_effect=requests.RequestException("boom")
        ):
            with self.assertRaises(auth.AuthError):
                auth.request_tokens("https://example.com/app")


class SessionTests(unittest.TestCase):
    """The stored session is the username; the privateCode has nowhere to live."""

    def test_a_written_session_round_trips(self):
        fake = FakeSettings()
        with mock.patch.object(auth, "settings", fake):
            written = auth.write_session("narutoxd123", method="cloud")
            session = auth.read_session()
        self.assertEqual(sorted(written), ["at", "method", "username"])
        self.assertEqual(session["username"], "narutoxd123")
        self.assertEqual(session["method"], "cloud")
        self.assertTrue(session["at"] > 0)

    def test_a_malformed_stored_value_reads_as_signed_out(self):
        for stored in (
            "narutoxd123",
            ["narutoxd123"],
            {"username": ""},
            {"username": None},
            {"username": "   "},
            7,
        ):
            with self.subTest(stored=stored):
                fake = FakeSettings({auth.AUTH_SESSION_KEY: stored})
                with mock.patch.object(auth, "settings", fake):
                    self.assertIsNone(auth.read_session())

    def test_a_blank_username_is_never_written(self):
        fake = FakeSettings()
        with mock.patch.object(auth, "settings", fake):
            self.assertIsNone(auth.write_session("   "))
            self.assertIsNone(auth.read_session())
        self.assertEqual(fake.values, {})

    def test_the_written_session_has_nowhere_for_a_private_code(self):
        fake = FakeSettings()
        with mock.patch.object(auth, "settings", fake):
            auth.write_session("narutoxd123", method="cloud")
        self.assertEqual(
            sorted(fake.values[auth.AUTH_SESSION_KEY]), ["at", "method", "username"]
        )

    def test_clear_session_signs_out(self):
        fake = FakeSettings()
        with mock.patch.object(auth, "settings", fake):
            auth.write_session("narutoxd123", method="cloud")
            auth.clear_session()
            self.assertIsNone(auth.read_session())

    def test_current_username_follows_the_stored_session(self):
        fake = FakeSettings()
        with mock.patch.object(auth, "settings", fake):
            self.assertEqual(auth.current_username(), "")
            auth.write_session("narutoxd123", method="cloud")
            self.assertEqual(auth.current_username(), "narutoxd123")
            auth.clear_session()
            self.assertEqual(auth.current_username(), "")

    def test_current_username_ignores_a_malformed_stored_value(self):
        for stored in ("narutoxd123", {"username": "   "}, 7, None):
            with self.subTest(stored=stored):
                fake = FakeSettings({auth.AUTH_SESSION_KEY: stored})
                with mock.patch.object(auth, "settings", fake):
                    self.assertEqual(auth.current_username(), "")


class AuthorLabelTests(unittest.TestCase):
    def test_someone_elses_project_is_left_alone(self):
        self.assertEqual(auth.author_label("otro", "narutoxd123"), "@otro")
        self.assertEqual(auth.author_name("otro", "narutoxd123"), "otro")

    def test_your_own_project_carries_the_literal_marker(self):
        self.assertEqual(auth.author_label("narutoxd123", "narutoxd123"), "@narutoxd123 (You)")
        self.assertEqual(auth.author_name("narutoxd123", "narutoxd123"), "narutoxd123 (You)")

    def test_usernames_are_compared_case_insensitively(self):
        self.assertTrue(auth.is_own_project("NarutoXD123", "narutoxd123"))
        self.assertEqual(auth.author_name("NarutoXD123", "narutoxd123"), "NarutoXD123 (You)")

    def test_an_empty_author_or_session_never_matches(self):
        self.assertFalse(auth.is_own_project("", "narutoxd123"))
        self.assertFalse(auth.is_own_project("narutoxd123", ""))
        self.assertFalse(auth.is_own_project("", ""))
        self.assertEqual(auth.author_label(""), "")
        self.assertEqual(auth.author_name("  ", "narutoxd123"), "")
        self.assertEqual(auth.author_label("narutoxd123", ""), "@narutoxd123")


if __name__ == "__main__":
    unittest.main()
