import json
import os
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from betbot import pages, vk, vk_rss


class VKRSSFormattingTests(unittest.TestCase):
    def news(self):
        return dict(id=1, title="Игорь Денисов о футболистах в Европе", body="Игрок Игорь Денисов обсудил РПЛ и клуб «Зенит».",
                    sport="football", t="2026-11-14T10:01:00Z", url="news/1.html", desc="Футбольная новость", photo="https://example.test/image.jpg")

    def test_small_relevant_unique_tag_set_without_betting_tags(self):
        tags = vk_rss.hashtags(self.news()).split()
        self.assertIn("#Футбол", tags)
        self.assertIn("#РПЛ", tags)
        self.assertIn("#ИгорьДенисов", tags)
        self.assertIn("#Зенит", tags)
        self.assertIn("#АИСТАВИТ", tags)
        self.assertEqual(len(tags), len(set(tags)))
        self.assertLessEqual(len(tags), 6)
        self.assertNotIn("#ставкинаспорт", tags)

    def test_short_link_cache_does_not_change_guid_or_image(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "vk_rss_since.txt").write_text("2026-11-14T09:00:00Z")
            (root / "vk_rss_format_since.txt").write_text("2026-11-14T10:00:00Z")
            image = root / "docs/rss-images/1.jpg"
            image.parent.mkdir(parents=True)
            image.write_bytes(b"jpeg")
            with patch.object(pages, "DATA", root), patch.object(pages, "DOCS", root / "docs"), \
                    patch.dict(os.environ, {"VK_TOKEN": "group", "VK_USER_TOKEN": ""}), \
                    patch.object(vk, "_call", return_value={"short_url": "https://vk.cc/example"}) as api:
                feed = ET.fromstring(pages._vk_rss([self.news()], pd.Timestamp("2026-11-14T11:00:00Z")))
                pages._vk_rss([self.news()], pd.Timestamp("2026-11-14T11:01:00Z"))
                self.assertEqual(api.call_count, 1)
            item = feed.find("channel/item")
            self.assertEqual(item.findtext("link"), "https://vk.cc/example")
            self.assertEqual(item.findtext("guid"), pages.SITE + "news/1.html")
            self.assertEqual(item.find("enclosure").attrib["url"], pages.SITE + "rss-images/1.jpg")
            self.assertIn("#ИгорьДенисов", item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded"))
            self.assertEqual(json.loads((root / "vk_rss_links.json").read_text())[pages.SITE + "news/1.html"], "vk.cc/example")

    def test_short_link_failure_holds_new_entry_instead_of_leaking_long_url(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "vk_rss_since.txt").write_text("2026-11-14T09:00:00Z")
            (root / "vk_rss_format_since.txt").write_text("2026-11-14T10:00:00Z")
            with patch.object(pages, "DATA", root), patch.object(pages, "DOCS", root / "docs"), \
                    patch.object(vk, "_short", side_effect=vk.ShortLinkError("unavailable")):
                feed = ET.fromstring(pages._vk_rss([self.news()], pd.Timestamp("2026-11-14T11:00:00Z")))
            self.assertFalse(feed.findall("channel/item"))


if __name__ == "__main__":
    unittest.main()
