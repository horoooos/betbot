import os
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


if __name__ == "__main__":
    unittest.main()
