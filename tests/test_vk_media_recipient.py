import unittest
from unittest.mock import patch
from tools import vk_media_check


class RecipientTests(unittest.TestCase):
    def test_public_photo_reference_accepts_user_and_group_owners(self):
        for reference in ("photo-123_456", "photo123_456"):
            self.assertEqual(vk_media_check.public_photo_reference(reference), reference)

    def test_public_photo_reference_rejects_cdn_urls_and_access_keys(self):
        for reference in ("https://example.test/image.jpg", "photo-123_456_private", "photo0_0"):
            with self.assertRaises(RuntimeError):
                vk_media_check.public_photo_reference(reference)

    def test_numeric_profile_does_not_need_resolution(self):
        with patch.object(vk_media_check, "call") as api:
            self.assertEqual(vk_media_check.resolve_recipient("group", "https://vk.com/id1234"), 1234)
            api.assert_not_called()

    def test_named_profile_is_resolved_to_user(self):
        with patch.object(vk_media_check, "call", return_value={"type": "user", "object_id": 1234}):
            self.assertEqual(vk_media_check.resolve_recipient("group", "https://vk.ru/example_user"), 1234)

    def test_group_is_not_accepted_as_recipient(self):
        with patch.object(vk_media_check, "call", return_value={"type": "group", "object_id": 1234}):
            with self.assertRaises(RuntimeError):
                vk_media_check.resolve_recipient("group", "https://vk.com/example_group")


if __name__ == "__main__":
    unittest.main()
