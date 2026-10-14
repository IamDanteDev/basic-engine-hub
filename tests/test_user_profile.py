"""The Scratch profile view's data comes from the users endpoint.

Run with: python -m unittest discover -s tests

The signed-in user's profile (avatar, description, status, country) cannot be
read from the browser — `api.scratch.mit.edu` sends no CORS headers, which is why
the web shows a username and nothing else — but the desktop shell talks to it
from Python, so the normalization lives here and is pinned here.

Deliberately imports nothing from PySide6: the CI runner does not install it.
"""

import unittest
from unittest.mock import patch

import requests

from hub import scratch_api

PROFILE_PAYLOAD = {
    "id": 78902785,
    "username": "narutoxd123",
    "scratchteam": False,
    "history": {"joined": "2021-06-24T21:31:43.000Z"},
    "profile": {
        "id": 77941991,
        "images": {
            "90x90": "https://cdn2.scratch.mit.edu/get_image/user/78902785_90x90.png?v=",
            "50x50": "https://cdn2.scratch.mit.edu/get_image/user/78902785_50x50.png?v=",
        },
        "status": "IDK",
        "bio": "soy youtuber y programador",
        "country": "Chile",
    },
}


class FakeResponse:
    def __init__(self, payload=None, status_code=200):
        self._payload = payload
        self.status_code = status_code
        self.text = ""

    def json(self):
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class UserProfileTests(unittest.TestCase):
    def test_the_profile_is_normalized_from_the_users_endpoint(self):
        with patch(
            "hub.scratch_api.requests.get", return_value=FakeResponse(PROFILE_PAYLOAD)
        ) as get:
            profile = scratch_api.fetch_user_profile("narutoxd123")
        self.assertEqual(get.call_args[0][0], "https://api.scratch.mit.edu/users/narutoxd123")
        self.assertEqual(profile["username"], "narutoxd123")
        self.assertEqual(profile["id"], 78902785)
        self.assertEqual(profile["bio"], "soy youtuber y programador")
        self.assertEqual(profile["status"], "IDK")
        self.assertEqual(profile["country"], "Chile")
        self.assertEqual(profile["joined"], "2021-06-24T21:31:43.000Z")

    def test_the_avatar_is_the_90x90_image(self):
        with patch("hub.scratch_api.requests.get", return_value=FakeResponse(PROFILE_PAYLOAD)):
            profile = scratch_api.fetch_user_profile("narutoxd123")
        self.assertEqual(
            profile["avatar"],
            "https://cdn2.scratch.mit.edu/get_image/user/78902785_90x90.png?v=",
        )

    def test_a_profile_without_a_bio_or_country_still_works(self):
        payload = {"id": 1, "username": "someone", "profile": {}, "history": {}}
        with patch("hub.scratch_api.requests.get", return_value=FakeResponse(payload)):
            profile = scratch_api.fetch_user_profile("someone")
        self.assertEqual(profile["bio"], "")
        self.assertEqual(profile["status"], "")
        self.assertEqual(profile["country"], "")
        self.assertEqual(profile["joined"], "")
        self.assertEqual(profile["avatar"], "")

    def test_a_payload_without_a_username_is_refused(self):
        with patch("hub.scratch_api.requests.get", return_value=FakeResponse({"id": 1})):
            with self.assertRaises(scratch_api.ScratchAPIError):
                scratch_api.fetch_user_profile("ghost")

    def test_an_http_error_names_the_status(self):
        with patch("hub.scratch_api.requests.get", return_value=FakeResponse(status_code=404)):
            with self.assertRaises(scratch_api.ScratchAPIError) as caught:
                scratch_api.fetch_user_profile("nobody")
        self.assertIn("404", str(exception := caught.exception))

    def test_a_transport_failure_raises_the_scratch_error(self):
        with patch("hub.scratch_api.requests.get", side_effect=requests.RequestException("boom")):
            with self.assertRaises(scratch_api.ScratchAPIError):
                scratch_api.fetch_user_profile("narutoxd123")


if __name__ == "__main__":
    unittest.main()
