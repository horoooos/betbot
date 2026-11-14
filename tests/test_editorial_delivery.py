import json
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch

import pandas as pd
from betbot import pages, editorial_cards


class EditorialDeliveryTests(unittest.TestCase):
    def test_rss_waits_for_telegram_continuation_and_exports_its_last_sentence(self):
        main = {"id": 100, "t": "2026-11-14T10:00:00Z", "photo": "https://example.test/photo.jpg", "reply": None,
                "html": '⚽ Полная спортивная новость\n\n' + 'Первый абзац. ' * 70 + '\n\n👇 Продолжение — в ответе\n\n<a>#футбол</a>'}
        continuation = {"id": 101, "t": "2026-11-14T10:00:03Z", "photo": None, "reply": 100,
                        "html": '📖 Продолжение\n\nЗаключительный абзац, который нельзя потерять.\n\n<a>#футбол</a>'}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'vk_rss_since.txt').write_text('2026-11-14T09:00:00Z')
            image = root / 'docs/rss-images/100.jpg'
            image.parent.mkdir(parents=True)
            image.write_bytes(b'jpeg')
            with patch.object(pages, 'DATA', root), patch.object(pages, 'DOCS', root / 'docs'):
                partial = pages._news({100: main})
                self.assertFalse(partial[0]['complete'])
                self.assertFalse(ET.fromstring(pages._vk_rss(partial, pd.Timestamp('2026-11-14T11:00:00Z'))).findall('channel/item'))
                complete = pages._news({100: main, 101: continuation})
                self.assertTrue(complete[0]['complete'])
                feed = ET.fromstring(pages._vk_rss(complete, pd.Timestamp('2026-11-14T11:00:00Z')))
                body = feed.findtext('channel/item/{http://purl.org/rss/1.0/modules/content/}encoded')
                self.assertIn('Заключительный абзац, который нельзя потерять.', body)
                self.assertGreater(len(body), 1024)
                self.assertIn('Заключительный абзац, который нельзя потерять.', feed.findtext('channel/item/description'))
                article = ET.fromstring(pages._vk_rss(complete, pd.Timestamp('2026-11-14T11:00:00Z'), article=True))
                article_body = article.findtext('channel/item/{http://purl.org/rss/1.0/modules/content/}encoded')
                self.assertIn('<p>', article_body)
                self.assertNotIn('<pre', article_body)
                self.assertIn('Заключительный абзац, который нельзя потерять.', article_body)
                seed = {**complete[0], 't': '2026-11-14T10:30:00Z', 'title': 'Полная версия: новость', 'url': 'news/full-100.html'}
                (root / 'vk_rss_article_seed.json').write_text(json.dumps(seed, default=str), encoding='utf-8')
                ordinary = ET.fromstring(pages._vk_rss(complete, pd.Timestamp('2026-11-14T11:00:00Z')))
                article = ET.fromstring(pages._vk_rss(complete, pd.Timestamp('2026-11-14T11:00:00Z'), article=True))
                self.assertEqual(len(ordinary.findall('channel/item')), 1)
                self.assertEqual(article.findtext('channel/item/title'), 'Полная версия: новость')

    def test_match_visual_uses_exact_team_metadata_without_forecast_fields(self):
        source = {"one": {"home": {"ru": "Сборная Японии", "logo": "japan", "color": "000555"},
                          "away": {"ru": "Сборная Бразилии", "logo": "brazil", "color": "fee000"},
                          "tip": "П1", "odds": 2, "sport": "football"}}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'matches.json').write_text(json.dumps(source), encoding='utf-8')
            with patch.object(editorial_cards, 'DATA', root):
                home, away, league, sport = editorial_cards.match_details('🔴 МАТЧ НАЧАЛСЯ\n⚽ Сборная Японии — Сборная Бразилии\n🏆 Сборные')
        self.assertEqual(home['logo'], 'japan')
        self.assertEqual(away['logo'], 'brazil')
        self.assertEqual(set(home), {'ru', 'logo', 'color'})
        self.assertEqual(sport, 'football')


if __name__ == '__main__':
    unittest.main()
