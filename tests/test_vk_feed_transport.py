import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
from html import unescape

import pandas as pd
from betbot import pages


class VKFeedTransportTests(unittest.TestCase):
    def test_both_vk_feeds_use_same_ascii_source_and_guid_only_for_new_news(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);docs=root/'docs'
            for name,value in [('vk_rss_since.txt','2026-11-14T00:00:00Z'),('vk_rss_format_since.txt','2026-11-14T00:00:00Z'),
                               ('vk_rss_ascii_since.txt','2026-11-14T00:00:00Z'),('vk_rss_unified_since.txt','2026-11-15T12:00:00Z')]:
                (root/name).write_text(value)
            images=docs/'rss-images';images.mkdir(parents=True)
            news=[]
            for i,hour in [(1,11),(2,13)]:
                (images/f'{i}.jpg').write_bytes(b'jpeg')
                news.append(dict(id=i,title='🎾 Андреева сравнили с Шараповой',sport='tennis',photo='https://example.test/photo.jpg',
                    url=f'news/{i}.html',body='Первый абзац.\n\nЗаключительный абзац.',desc='Новость',complete=True,t=f'2026-11-15T{hour}:00:00Z'))
            with patch.object(pages,'DATA',root),patch.object(pages,'DOCS',docs),patch('betbot.vk._short',return_value='vk.cc/test'):
                for article in (False,True):
                    wire=pages._vk_rss(news,pd.Timestamp('2026-11-15T14:00:00Z'),article=article)
                    self.assertTrue(wire.isascii())
                    for encoding in ('utf-8','windows-1251','latin-1'):
                        items=ET.fromstring(wire.encode('ascii').decode(encoding)).findall('channel/item')
                        old=next(i for i in items if i.findtext('guid').endswith('news/1.html'))
                        new=next(i for i in items if i.findtext('guid').endswith('vk-articles/2.html'))
                        self.assertEqual(old.findtext('guid'),pages.SITE+'news/1.html')
                        self.assertEqual(new.findtext('guid'),pages.SITE+'vk-articles/2.html')
                        self.assertEqual(new.findtext('link'),new.findtext('guid'))
                        self.assertEqual(new.findtext('title'),'Андреева сравнили с Шараповой')
                        self.assertTrue(new.findtext('description').startswith('📊 Подробнее на сайте'))
                        body=unescape(new.findtext('{http://purl.org/rss/1.0/modules/content/}encoded'))
                        self.assertIn('#теннис',body)
                        self.assertIn('Заключительный абзац.',body)
                page=(docs/'vk-articles/2.html').read_bytes()
                self.assertTrue(page.isascii())
                self.assertIn('Андреева сравнили с Шараповой',unescape(page.decode('windows-1251')))


if __name__=='__main__':unittest.main()
