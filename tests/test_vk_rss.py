import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
from unittest.mock import Mock

import pandas as pd
from betbot import pages


class VKRSSFeedTests(unittest.TestCase):
    def test_vk_first_html_text_node_keeps_footer_and_is_ascii_transport(self):
        from html import unescape
        from html.parser import HTMLParser
        news = dict(id=1, title='Заголовок', t='2026-11-20T10:00:00Z', sport='football',
                    photo='https://example.test/a.jpg', body='Полный текст.\n\n#футбол #аиставит',
                    desc='Описание', url='news/1.html', vk_compact_rss=True, rss_link='https://vk.cc/example')
        xml = pages._rss([news], [], {}, pd.Timestamp('2026-11-20T10:01:00Z'), feed_name='rss-vk.xml')
        content = ET.fromstring(xml).findtext('channel/item/{http://purl.org/rss/1.0/modules/content/}encoded')
        self.assertTrue(content.isascii())
        self.assertNotIn('<br',content)
        class FirstNode(HTMLParser):
            def __init__(self):super().__init__(convert_charrefs=True);self.nodes=[]
            def handle_data(self,data):
                if data.strip():self.nodes.append(data)
        parser=FirstNode();parser.feed(content)
        self.assertIn('Полный текст.', parser.nodes[0]);self.assertIn('#аиставит',parser.nodes[0])
        self.assertIn('Подробнее на сайте',parser.nodes[0]);self.assertIn('vk.cc/example',parser.nodes[0])

    def test_sport_tag_does_not_turn_a_result_or_live_forecast_into_news(self):
        from betbot.vk_rss import is_news
        for title in ['ИТОГ · Испания · Сегунда · МИМО','LIVE-прогноз зашёл: ТМ 2.5','ПРОГНОЗ на матч','СТАТИСТИКА БОТА']:
            self.assertFalse(is_news({'title':title,'body':'Матч завершён.','sport':'football'}))
        self.assertTrue(is_news({'title':'Тренер рассказал о матче','body':'Полная новость.','sport':'football'}))

    def test_full_content_does_not_print_telegram_html_tags(self):
        from betbot.vk_rss import import_caption
        from html import unescape
        source=dict(title='Новость',sport='football',body='Первый <b>абзац</b>.\n\nВторой <a href="https://example.test">абзац</a>.',rss_link='https://vk.cc/test')
        text=unescape(__import__('re').sub('<[^>]+>','',import_caption(source)))
        self.assertIn('Первый абзац.\n\nВторой абзац.',text)
        self.assertNotIn('<b>',text);self.assertIn('#аиставит',text)

    def test_source_is_not_ready_until_article_and_cover_are_public(self):
        from betbot.vk_rss import public_source_ready
        page=Mock(status_code=200,text='<meta name="vk-source-format" content="full-news-2"><img src="https://example.test/photo.jpg">')
        with patch('requests.get',return_value=page),patch('requests.head',return_value=Mock(status_code=404,headers={})):
            self.assertFalse(public_source_ready('https://example.test/article','https://example.test/photo.jpg'))
        with patch('requests.get',return_value=page),patch('requests.head',return_value=Mock(status_code=200,headers={'Content-Type':'image/jpeg'})):
            self.assertTrue(public_source_ready('https://example.test/article','https://example.test/photo.jpg'))

    def test_news_only_filter_rejects_results_even_if_caller_passes_them(self):
        now=pd.Timestamp('2026-11-20T10:01:00Z')
        result=dict(id=2,title='Итог матча',t=now,sport='football',photo='https://example.test/a.jpg',body='Счёт',url='result.html',kind='result')
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);(root/'vk_rss_since.txt').write_text('2026-11-19T00:00:00Z')
            with patch.object(pages,'DATA',root),patch.object(pages,'DOCS',root/'docs'):
                self.assertEqual(ET.fromstring(pages._vk_rss([result],now)).findall('channel/item'),[])


    def test_results_require_photo_activation_and_final_tag(self):
        now = pd.Timestamp('2026-11-20T12:00:00Z')
        posts = {1:dict(t='2026-11-20T11:30:00Z', html='🎮 Итог матча\nПобеда команды.\n#итог', photo='https://example.test/result.jpg'),
                 2:dict(t='2026-11-20T11:31:00Z', html='🎮 КАРТА!\n#live', photo='https://example.test/map.jpg')}
        with tempfile.TemporaryDirectory() as directory, patch.object(pages, 'DATA', Path(directory)):
            self.assertEqual(pages._vk_results(posts, now), [])
            (Path(directory)/'vk_results_since.txt').write_text('2026-11-20T11:00:00Z')
            results = pages._vk_results(posts, now)
        self.assertEqual([p['id'] for p in results], [1])
        self.assertEqual(results[0]['sport'], 'esports')
        self.assertEqual(results[0]['kind'], 'result')

    def test_only_recent_illustrated_news_after_activation_are_imported(self):
        now = pd.Timestamp("2026-11-14T10:00:00Z")
        def news(title, timestamp, photo="https://example.test/photo.jpg"):
            return dict(id=123, title=title, t=timestamp, photo=photo, url=f"news/{title}.html",
                        body="Actual news body", desc="Description", sport="football")
        entries = [news("old", "2026-11-14T08:00:00Z"), news("fresh", "2026-11-14T09:30:00Z"),
                   news("no-image", "2026-11-14T09:40:00Z", ""), news("future", "2026-11-15T09:00:00Z")]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "vk_rss_since.txt").write_text("2026-11-14T09:00:00Z", encoding="utf-8")
            with patch.object(pages, "DATA", root), patch.object(pages, "DOCS", root / "docs"), \
                    patch.object(pages.requests, "get", return_value=Mock(content=b"source")) as download, \
                    patch("betbot.postimg.as_jpeg", return_value=b"jpeg"):
                feed = ET.fromstring(pages._vk_rss(entries, now))
                pages._vk_rss(entries, now)
                self.assertEqual(download.call_count, 1)
        items = feed.findall("channel/item")
        self.assertEqual([item.findtext("title") for item in items], ["fresh"])
        self.assertEqual(items[0].find("enclosure").attrib["url"], pages.SITE + "rss-images/123.jpg")
        self.assertEqual(items[0].find("enclosure").attrib["length"], "4")
        self.assertIn(f'<img src="{pages.SITE}rss-images/123.jpg">', items[0].findtext("{http://purl.org/rss/1.0/modules/content/}encoded"))
        self.assertEqual(feed.find("channel/{http://www.w3.org/2005/Atom}link").attrib["href"], pages.SITE + "rss-vk.xml")
        self.assertNotIn("прогноз", feed.findtext("channel/description").lower())


if __name__ == "__main__":
    unittest.main()
