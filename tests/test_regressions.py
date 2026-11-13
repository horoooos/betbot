"""Regression checks for VK publishing, name matching, and daily video retries."""
from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from betbot import dzen, names, postimg, shorts, vk


class VKPhotoTests(unittest.TestCase):
    def test_photo_upload_does_not_use_unverified_messages_photo_fallback_after_wall_flood(self):
        calls = []

        def api(method, _tok=None, **params):
            calls.append((method, _tok, params))
            if method == "photos.getWallUploadServer":
                raise RuntimeError("VK photos.getWallUploadServer: 9 Flood control")
            raise AssertionError(method)

        with patch.dict(os.environ, {"VK_USER_TOKEN": "user", "VK_TOKEN": "group"}), \
                patch.object(vk, "_call", side_effect=api), \
                patch("time.sleep"):
            self.assertIsNone(vk._photo(b"jpeg"))

        self.assertEqual([c[0] for c in calls], ["photos.getWallUploadServer"])
        self.assertIn("Flood control", vk._photo.err)

    def _crosspost(self, photo, *, short_fails=False, verify_fails=False, state=None, seeds=None):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        fake_file = root / "project" / "betbot" / "vk.py"
        fake_file.parent.mkdir(parents=True)
        fake_file.write_text("", encoding="utf-8")
        marker = root / "project" / "data" / "vk_resume.txt"
        marker.parent.mkdir(parents=True)
        channel = root / "channel.json"
        channel.write_text(json.dumps({"posts": {"5401": {
            "html": "Проверка публикации: команда А — команда Б.",
            "t": "2000-01-01T00:00:00+00:00",
        }}}, ensure_ascii=False), encoding="utf-8")

        calls = []
        full_link = "https://example.test/p/5401"

        def api(method, _tok=None, **params):
            calls.append((method, _tok, params))
            if method == "utils.getShortLink":
                if short_fails:
                    raise RuntimeError("VK utils.getShortLink: 5 authorization failed")
                return {"short_url": "https://vk.cc/abc123"}
            if method == "wall.post":
                return {"post_id": 77}
            if method == "wall.getById":
                if verify_fails:
                    raise RuntimeError("VK wall.getById: 9 Flood control")
                return {"items": [{"attachments": [{"type": "photo"}]}]}
            if method == "wall.getComments":
                return {"items": []}
            if method == "wall.createComment":
                return {"comment_id": 88}
            raise AssertionError(method)

        state = state or {
            "vk_last": 5400, "vk_pause_ts": 0, "vk_at_ts": 0,
            "vk_hour": {}, "vk_day": {}, "vk_photos": [], "vk_comment_pending": {},
        }
        photo_patcher = patch.object(vk, "_photo", return_value=photo)
        with patch.dict(os.environ, {"VK_USER_TOKEN": "user", "VK_TOKEN": "group"}), \
                patch.object(vk, "__file__", str(fake_file)), \
                patch.object(vk, "CHANNEL", channel), \
                patch.object(vk, "SEED_PHOTOS", seeds or []), \
                patch.object(vk, "_site_link", return_value=full_link), \
                patch.object(vk, "_call", side_effect=api), \
                photo_patcher, \
                patch.object(dzen, "hashtags", return_value=""), \
                patch.object(dzen, "kind", return_value="новость"), \
                patch.object(postimg, "image_for", return_value=b"image"):
            done = vk.crosspost(state)
        return done, state, calls, full_link

    def test_wall_post_has_photo_and_short_link_comment(self):
        photo = f"photo-{vk.GROUP_ID}_999"
        done, state, calls, full_link = self._crosspost(photo)
        self.assertEqual(done, 1)
        wall = next(c for c in calls if c[0] == "wall.post")
        self.assertEqual(wall[2]["attachments"], f"{photo},{full_link}")
        self.assertIn("vk.cc/abc123", wall[2]["message"])
        self.assertNotIn(full_link, wall[2]["message"])
        comment = next(c for c in calls if c[0] == "wall.createComment")
        self.assertEqual(comment[2]["message"], "🔗 Сайт проекта: vk.cc/abc123")
        self.assertEqual(state["vk_last"], 5401)

    def test_missing_photo_or_short_link_never_publishes_text_only(self):
        done, state, calls, _ = self._crosspost(None)
        self.assertEqual(done, 0)
        self.assertEqual(state["vk_last"], 5400)
        self.assertFalse(any(c[0] == "wall.post" for c in calls))

    def test_verification_flood_does_not_delete_or_duplicate_created_post(self):
        photo = f"photo-{vk.GROUP_ID}_999"
        state = {
            "vk_last": 5400, "vk_pause_ts": 0, "vk_at_ts": 0,
            "vk_hour": {}, "vk_day": {}, "vk_photos": [], "vk_comment_pending": {},
        }
        done, state, calls, _ = self._crosspost(photo, verify_fails=True, state=state)
        self.assertEqual(done, 0)
        self.assertEqual(state["vk_last"], 5400)
        self.assertEqual(state["vk_verify_pending"]["post_id"], 77)
        self.assertEqual(sum(c[0] == "wall.post" for c in calls), 1)
        self.assertFalse(any(c[0] == "wall.delete" for c in calls))
        self.assertGreater(state["vk_verify_retry_at"], time.time() + vk.PAUSE_S - 5)

        done, state, calls, _ = self._crosspost(photo, state=state)
        self.assertEqual(done, 0)
        self.assertEqual(state["vk_last"], 5400)
        self.assertFalse(calls)  # не опрашиваем VK постоянно во время паузы
        state["vk_verify_retry_at"] = 0

        done, state, calls, _ = self._crosspost(photo, state=state)
        self.assertEqual(done, 0)
        self.assertEqual(state["vk_last"], 5401)
        self.assertNotIn("vk_verify_pending", state)
        self.assertFalse(any(c[0] == "wall.post" for c in calls))

    def test_failed_upload_never_publishes_cached_or_seed_photo(self):
        state = {"vk_last": 5400, "vk_photos": ["photo-1_123"]}
        done, state, calls, _ = self._crosspost(None, state=state, seeds=["photo-1_456"])
        self.assertEqual(done, 0)
        self.assertEqual(state["vk_last"], 5400)
        self.assertFalse(any(c[0] == "wall.post" for c in calls))

        done, state, calls, _ = self._crosspost(f"photo-{vk.GROUP_ID}_999", short_fails=True)
        self.assertEqual(done, 0)
        self.assertEqual(state["vk_last"], 5400)
        self.assertFalse(any(c[0] == "wall.post" for c in calls))

    def test_legacy_verification_flood_retry_is_extended_once_without_api_calls(self):
        state = {"vk_verify_pending": {"pid": 5401, "post_id": 77},
                 "vk_verify_retry_at": 1900, "vk_pause_ts": 0,
                 "vk_err": "VK wall.getById: 9 Flood control"}
        with patch.object(vk.time, "time", return_value=2000), patch.object(vk, "_call") as api:
            self.assertTrue(vk._resolve_pending_post(state))
            self.assertEqual(state["vk_verify_retry_at"], 4600)
            self.assertTrue(vk._resolve_pending_post(state))
            self.assertEqual(state["vk_verify_retry_at"], 4600)
            api.assert_not_called()

    def test_resume_marker_is_only_consumed_once_if_git_restores_it(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fake_file = root / "project" / "betbot" / "vk.py"
            fake_file.parent.mkdir(parents=True)
            fake_file.write_text("", encoding="utf-8")
            marker = root / "project" / "data" / "vk_resume.txt"
            marker.parent.mkdir(parents=True)
            marker.write_text("resume", encoding="utf-8")
            channel = root / "channel.json"
            channel.write_text(json.dumps({"posts": {"9999": {
                "html": "Проверка сигнала возобновления публикаций.",
                "t": "2000-01-01T00:00:00+00:00",
            }}}, ensure_ascii=False), encoding="utf-8")
            state = {"vk_last": 9998, "vk_pause_ts": time.time() + 5000, "vk_floods": 3,
                     "vk_err": "flood", "vk_at_ts": time.time()}
            with patch.dict(os.environ, {"VK_TOKEN": "group"}), \
                    patch.object(vk, "__file__", str(fake_file)), patch.object(vk, "CHANNEL", channel):
                self.assertEqual(vk.crosspost(state), 0)
                self.assertEqual(state["vk_resume_key"], "resume")
                self.assertEqual(state["vk_pause_ts"], 0)
                marker.write_text("resume", encoding="utf-8")  # same tracked file returns after git pull
                state["vk_pause_ts"] = time.time() + 5000
                self.assertEqual(vk.crosspost(state), 0)
                self.assertGreater(state["vk_pause_ts"], time.time())
                self.assertEqual(state["vk_floods"], 0)


class NameAndShortsTests(unittest.TestCase):
    def test_russian_team_names_do_not_collapse_to_empty(self):
        self.assertEqual(names.norm("Спартак Москва"), "спартак москва")
        self.assertEqual(names.norm("Зенит Санкт-Петербург"), "зенит санкт петербург")
        self.assertLess(names.similarity("Спартак Москва", "Зенит Санкт-Петербург"), 0.5)
        self.assertGreater(names.similarity("Manchester United", "Manchester Utd"), 0.5)

    def test_short_video_render_retries_with_backoff_then_stops(self):
        now = pd.Timestamp("2026-11-14 12:00", tz="Europe/Moscow")
        state = {}
        results = pd.DataFrame({"dummy": [1]})
        with patch.object(shorts, "clip_best", return_value=(None, None)) as build:
            shorts.run(state, now, results)
            self.assertEqual(state["shorts_retry_attempts"], 1)
            self.assertNotIn("shorts_day", state)
            shorts.run(state, now + pd.Timedelta(minutes=10), results)
            self.assertEqual(build.call_count, 1)
            shorts.run(state, now + pd.Timedelta(minutes=16), results)
            self.assertEqual(state["shorts_retry_attempts"], 2)
            shorts.run(state, now + pd.Timedelta(minutes=32), results)
            self.assertEqual(state["shorts_retry_attempts"], 3)
            self.assertEqual(state["shorts_day"], "2026-11-14")
            shorts.run(state, now + pd.Timedelta(minutes=34), results)
            self.assertEqual(build.call_count, 3)


if __name__ == "__main__":
    unittest.main()
