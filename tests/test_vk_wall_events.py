import unittest
from unittest.mock import Mock, patch
from betbot import vk
from betbot.vk_wall_events import PhotoMonitor


class WallEventTests(unittest.TestCase):
    def test_enabling_wall_events_preserves_other_settings(self):
        with patch.object(vk, "_call", side_effect=[{"is_enabled": True, "api_version": "5.131",
                                                    "events": {"message_new": True, "wall_post_new": False}},
                                                   1, {"server": "https://example.test", "key": "secret", "ts": "1"}]) as api:
            PhotoMonitor("group").start()
            params = api.call_args_list[1].kwargs
            self.assertEqual(params["message_new"], 1)
            self.assertEqual(params["wall_post_new"], 1)
            self.assertEqual(params["api_version"], "5.131")

    def test_photo_is_verified_only_for_matching_post(self):
        monitor = PhotoMonitor("group")
        monitor.server = {"server": "https://example.test", "key": "secret", "ts": "1"}
        response = Mock()
        response.json.return_value = {"ts": "2", "updates": [
            {"type": "wall_post_new", "group_id": vk.GROUP_ID, "object": {"id": 42, "attachments": [{"type": "photo"}]}}]}
        with patch("betbot.vk_wall_events.requests.get", return_value=response):
            self.assertTrue(monitor.verify(42))
        self.assertEqual(monitor.server["ts"], "2")


if __name__ == "__main__":
    unittest.main()
