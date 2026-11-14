import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from betbot import pages


class VKRSSFeedTests(unittest.TestCase):
    def test_only_recent_illustrated_news_after_activation_are_imported(self):
        now = pd.Timestamp("2026-11-14T10:00:00Z")
        def news(title, timestamp, photo="https://example.test/photo.jpg"):
            return dict(title=title, t=timestamp, photo=photo, url=f"news/{title}.html",
                        body="Actual news body", desc="Description", sport="football")
        entries = [news("old", "2026-11-14T08:00:00Z"), news("fresh", "2026-11-14T09:30:00Z"),
                   news("no-image", "2026-11-14T09:40:00Z", ""), news("future", "2026-11-15T09:00:00Z")]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "vk_rss_since.txt").write_text("2026-11-14T09:00:00Z", encoding="utf-8")
            with patch.object(pages, "DATA", root):
                feed = ET.fromstring(pages._vk_rss(entries, now))
        items = feed.findall("channel/item")
        self.assertEqual([item.findtext("title") for item in items], ["fresh"])
        self.assertEqual(items[0].find("enclosure").attrib["url"], "https://example.test/photo.jpg")
        self.assertIn('<img src="https://example.test/photo.jpg">', items[0].findtext("{http://purl.org/rss/1.0/modules/content/}encoded"))
        self.assertEqual(feed.find("channel/{http://www.w3.org/2005/Atom}link").attrib["href"], pages.SITE + "rss-vk.xml")
        self.assertNotIn("прогноз", feed.findtext("channel/description").lower())


if __name__ == "__main__":
    unittest.main()
