import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from hub import cache, settings
from hub.catalog import (
    BLOCKED_PROJECT_IDS,
    FEATURED_PROJECT_ID,
    PINNED_PROJECT_IDS,
    SOURCE_USER,
    STUDIO_ID,
)


class CacheTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = Path(self.temp.name)
        self.data = root / "data"
        self.legacy = root / "legacy"
        self.projects = self.data / "projects"
        self.thumbnails = self.data / "thumbnails"
        self.avatars = self.data / "avatars"
        self.legacy_projects = self.legacy / "projects"
        self.legacy_thumbnails = self.legacy / "thumbnails"
        self.legacy_avatars = self.legacy / "avatars"
        for directory in (
            self.projects,
            self.thumbnails,
            self.avatars,
            self.legacy_projects,
            self.legacy_thumbnails,
            self.legacy_avatars,
        ):
            directory.mkdir(parents=True)
        replacements = {
            "PROJECTS": self.projects,
            "THUMBNAILS": self.thumbnails,
            "AVATARS": self.avatars,
            "INDEX": self.data / "cache.json",
            "LEGACY_PROJECTS": self.legacy_projects,
            "LEGACY_THUMBNAILS": self.legacy_thumbnails,
            "LEGACY_AVATARS": self.legacy_avatars,
            "LEGACY_INDEX": self.legacy / "cache.json",
        }
        for name, value in replacements.items():
            context = patch.object(cache, name, value)
            context.start()
            self.addCleanup(context.stop)

    def tearDown(self):
        self.temp.cleanup()

    def test_discovers_legacy_projects_and_metadata(self):
        (self.legacy_projects / "42.sb3").write_bytes(b"project")
        cache.LEGACY_INDEX.write_text(
            json.dumps({"42": {"title": "Old project", "username": "maker"}}),
            encoding="utf-8",
        )

        self.assertTrue(cache.is_cached(42))
        self.assertEqual(cache.find_project_path(42), self.legacy_projects / "42.sb3")
        self.assertEqual(
            cache.cached_projects(),
            [{
                "id": 42,
                "title": "Old project",
                "username": "maker",
                "creator_id": 0,
                "image": "",
                "avatar": "",
            }],
        )

    def test_clear_removes_projects_but_keeps_media(self):
        (self.projects / "12.sb3").write_bytes(b"data")
        (self.legacy_projects / "13.sb3").write_bytes(b"data")
        (self.thumbnails / "12.png").write_bytes(b"image")
        (self.avatars / "9.png").write_bytes(b"image")

        self.assertEqual(cache.clear_project_cache(), 2)
        self.assertFalse(cache.is_cached(12))
        self.assertTrue((self.thumbnails / "12.png").is_file())
        self.assertTrue((self.avatars / "9.png").is_file())

    def test_index_writes_to_xdg_cache(self):
        cache.record_entry(5, title="New")

        self.assertEqual(json.loads((self.data / "cache.json").read_text()), {"5": {"title": "New"}})

    def test_xdg_index_keeps_metadata_for_legacy_projects(self):
        cache.LEGACY_INDEX.write_text(
            json.dumps({"42": {"title": "Legacy"}}), encoding="utf-8"
        )
        cache.INDEX.write_text(
            json.dumps({"9": {"title": "Current"}}), encoding="utf-8"
        )

        self.assertEqual(
            cache.load_index(),
            {"42": {"title": "Legacy"}, "9": {"title": "Current"}},
        )


class SettingsTests(unittest.TestCase):
    def test_reads_legacy_then_writes_xdg(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "settings.json"
            destination = root / "config" / "settings.json"
            legacy.write_text('{"language":"en"}', encoding="utf-8")
            with patch.object(settings, "LEGACY_PATH", legacy), patch.object(settings, "PATH", destination):
                self.assertEqual(settings.get("language"), "en")
                settings.set("language", "es")
                self.assertEqual(json.loads(destination.read_text()), {"language": "es"})
                self.assertEqual(json.loads(legacy.read_text()), {"language": "en"})


class CatalogTests(unittest.TestCase):
    def test_web_and_desktop_share_listing_configuration(self):
        from web import listing

        self.assertEqual(listing.STUDIO_ID, STUDIO_ID)
        self.assertEqual(listing.SOURCE_USER, SOURCE_USER)
        self.assertEqual(listing.BLOCKED_PROJECT_IDS, BLOCKED_PROJECT_IDS)
        self.assertEqual(listing.PINNED_PROJECT_IDS, PINNED_PROJECT_IDS)
        self.assertEqual(listing.FEATURED_PROJECT_ID, FEATURED_PROJECT_ID)

    def test_build_listing_flags_featured_and_inserted_pinned(self):
        from web.listing import build_listing

        studio_page = [
            {"id": 300, "title": "Recent", "username": "author"},
            {"id": FEATURED_PROJECT_ID, "title": "Featured", "username": "author"},
            {"id": 100, "title": "Old", "username": "author"},
        ]

        def fake_fetch(url):
            if "studios/" in url:
                return studio_page
            if "users/" in url:
                return []
            if url.endswith("/projects/1192855606"):
                return {"id": 1192855606, "title": "Pinned", "author": {"username": "author"}}
            raise RuntimeError(f"unexpected url: {url}")

        with patch("web.listing.fetch_json", side_effect=fake_fetch):
            built = build_listing()

        by_id = {project["id"]: project for project in built}
        self.assertTrue(by_id[FEATURED_PROJECT_ID].get("featured"))
        self.assertTrue(by_id[1192855606].get("pinned"))
        self.assertNotIn("featured", by_id[300])
        self.assertNotIn("pinned", by_id[300])

    def test_pages_detail_enrichment_is_best_effort_and_normalized(self):
        from web.listing import _enrich_details

        payload = {
            "description": "Description",
            "instructions": "Instructions",
            "comments_allowed": True,
            "stats": {"views": "12", "loves": 4, "favorites": None, "remixes": "bad"},
        }
        projects = [{"id": 42, "title": "Project"}, {"id": 99, "title": "Unavailable"}]

        def detail_for(url):
            if url.endswith("/42"):
                return payload
            raise RuntimeError("offline")

        with patch("web.listing.fetch_json", side_effect=detail_for):
            result = _enrich_details(projects)

        by_id = {project["id"]: project for project in result}
        self.assertEqual(by_id[42]["description"], "Description")
        self.assertEqual(by_id[42]["stats"], {"views": 12, "loves": 4, "favorites": 0, "remixes": 0})
        self.assertNotIn("description", by_id[99])


if __name__ == "__main__":
    unittest.main()