import os
import json
import tempfile
from pathlib import Path
from datetime import datetime, timezone
from io import BytesIO
import unittest
from unittest.mock import patch

from PIL import Image
from betbot import vk, vk_stories


class StoryTests(unittest.TestCase):
    def image(self):
        result = BytesIO()
        Image.new("RGB", (800, 450), "blue").save(result, "JPEG")
        return result.getvalue()

    def test_portrait_is_valid_vertical_jpeg(self):
        with Image.open(BytesIO(vk_stories.portrait(self.image(), "Новость", True))) as image:
            self.assertEqual(image.size, (1080, 1920))
            self.assertEqual(image.format, "JPEG")

    def publish(self, verified):
        story = {"owner_id": -vk.GROUP_ID, "id": 123, "type": "photo", "photo": {"id": 456}}
        with patch.dict(os.environ, {"VK_TOKEN": "group", "VK_USER_TOKEN": "unused"}), \
                patch.object(vk_stories, "_upload", return_value="uploaded"), \
                patch.object(vk_stories.time, "sleep"), \
                patch.object(vk, "_call", side_effect=[{"upload_url": "https://example.test/upload"},
                                                      {"items": [story]}, {"items": [verified or story]}]) as api:
            result = vk_stories.publish_image(self.image(), test=True)
            self.assertEqual([c.args[0] for c in api.call_args_list],
                             ["stories.getPhotoUploadServer", "stories.save", "stories.getById"])
            self.assertTrue(all(c.kwargs["_tok"] == "group" for c in api.call_args_list))
            return result

    def test_story_uses_group_token_and_verifies_photo(self):
        self.assertEqual(self.publish(None)["id"], 123)

    def test_missing_photo_is_not_reported_as_success(self):
        with self.assertRaises(RuntimeError):
            self.publish({"owner_id": -vk.GROUP_ID, "id": 123, "type": "photo"})

    def test_pending_story_is_verified_without_republishing(self):
        story = {"owner_id": -vk.GROUP_ID, "id": 123, "type": "photo", "photo": {"id": 456}}
        state = {"vk_story_last": 100}

        def created(image, text, **callbacks):
            callbacks["on_saving"]()
            callbacks["on_saved"](story)
            raise RuntimeError("VK stories.getById: 9 Flood control")

        with tempfile.TemporaryDirectory() as folder:
            channel = Path(folder) / "channel.json"
            channel.write_text(json.dumps({"posts": {"101": {"html": "Новость спорта", "t": datetime.now(timezone.utc).isoformat()}}}), encoding="utf-8")
            with patch.dict(os.environ, {"VK_STORIES_ENABLED": "1", "VK_TOKEN": "group"}), \
                    patch.object(vk, "CHANNEL", channel), \
                    patch("betbot.dzen.kind", return_value="новость"), \
                    patch("betbot.postimg.image_for", return_value=self.image()), \
                    patch.object(vk_stories, "publish_image", side_effect=created) as publish, \
                    patch.object(vk_stories, "verify_story", return_value=story) as verify:
                self.assertEqual(vk_stories.crosspost(state), 0)
                self.assertEqual(state["vk_story_pending"]["id"], 123)
                self.assertEqual(state["vk_story_last"], 100)
                self.assertEqual(vk_stories.crosspost(state), 0)
                verify.assert_not_called()
                state["vk_story_retry_at"] = 0
                self.assertEqual(vk_stories.crosspost(state), 1)
                self.assertEqual(state["vk_story_last"], 101)
                self.assertNotIn("vk_story_pending", state)
                self.assertEqual(vk_stories.crosspost(state), 0)
                self.assertEqual(publish.call_count, 1)


if __name__ == "__main__":
    unittest.main()
