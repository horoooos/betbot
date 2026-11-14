import json
import os
import re
from html.parser import HTMLParser
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
        self.assertIn("#футбол", tags)
        self.assertIn("#РПЛ", tags)
        self.assertIn("#Денисов", tags)
        self.assertIn("#аиставит", tags)
        self.assertEqual(len(tags), len(set(tags)))
        self.assertLessEqual(len(tags), 8)
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
            body = item.findtext("{http://purl.org/rss/1.0/modules/content/}encoded")
            self.assertIn("#Денисов", body)
            self.assertIn("Подробнее на сайте 👉 vk.cc/example", body)
            plain = re.sub(r"<[^>]+>", "", body).strip()
            self.assertIn("клуб «Зенит».\n\n#футбол\n\n📊 Подробнее", plain)
            self.assertIn("vk.cc/example\n\n#РПЛ #Денисов", plain)
            class TextOnly(HTMLParser):
                def __init__(self):
                    super().__init__()
                    self.parts = []
                def handle_data(self, data):
                    if data.strip():
                        self.parts.append(data.strip())
            importer = TextOnly()
            importer.feed(body)
            self.assertIn("клуб «Зенит».\n\n#футбол\n\n📊 Подробнее", "".join(importer.parts))
            self.assertTrue(item.findtext("title").startswith("⚽ "))
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

    def test_reference_post_uses_surname_league_and_requested_footer(self):
        news = self.news()
        news.update(title="Галактионову оформили прогул за отсутствие на тренировке",
                    body="Тренер «Локомотива» Михаил Галактионов пропустил тренировку.\n\n⚽ Команда выступает в РПЛ.")
        with patch.object(vk, "_short", return_value="vk.cc/reference"):
            post = vk_rss.prepare(news, {})
        self.assertIn("#РПЛ #Галактионов #новостиспорта #спорт #главное #аиставит", post["body"])
        self.assertIn("\n\n#футбол\n\n📊 Подробнее на сайте 👉 vk.cc/reference", post["body"])
        self.assertNotIn("#Локомотива", post["body"])
        self.assertNotIn("#МихаилГалактионов", post["body"])
        self.assertIn("📰 Тренер", post["body"])


if __name__ == "__main__":
    unittest.main()
