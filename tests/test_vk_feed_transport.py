import tempfile
import re
import json
import os
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path
from unittest.mock import patch
from html import unescape

import pandas as pd
from betbot import pages


class VKFeedTransportTests(unittest.TestCase):
    def test_actual_vk_content_field_contains_finished_caption_not_long_article(self):
        # Regression for the Simon screenshot: description already had hashtags
        # but VK displayed/truncated the long content:encoded before the footer.
        from bs4 import BeautifulSoup
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);docs=root/'docs';images=docs/'rss-images';images.mkdir(parents=True)
            for name in ('vk_rss_since.txt','vk_rss_format_since.txt','vk_rss_ascii_since.txt','vk_rss_unified_since.txt','vk_rss_footer_since.txt','vk_rss_caption_since.txt'):
                (root/name).write_text('2026-11-15T00:00:00Z')
            # This item predates the rollout but may still be waiting in VK's
            # import queue. Its actual content must be bounded as well.
            (root/'vk_rss_caption_since.txt').write_text('2026-11-15T12:30:00Z')
            (images/'6219.jpg').write_bytes(b'jpeg')
            tail='Заключительная фраза полной статьи сохранена целиком.'
            news=dict(id=6219,title='Унаи Симон получил трофей',sport='football',photo='https://example.test/image.jpg',
                url='news/6219.html',body='Первый законченный абзац.\n\n'+'Расулов подчеркнул важность игры вратаря. '*70+'\n\n'+tail,
                desc='Новость',complete=True,t='2026-11-15T12:00:00Z')
            with patch.object(pages,'DATA',root),patch.object(pages,'DOCS',docs),patch('betbot.vk._short',return_value='vk.cc/test'):
                for article in (False,True):
                    item=ET.fromstring(pages._vk_rss([news],pd.Timestamp('2026-11-15T13:00:00Z'),article=article)).find('channel/item')
                    body=BeautifulSoup(item.findtext('{http://purl.org/rss/1.0/modules/content/}encoded'),'html.parser')
                    text=body.get_text('\n\n',strip=True)
                    self.assertEqual(text,item.findtext('description'))
                    self.assertLessEqual(len(text),420)
                    self.assertIn('#аиставит',text)
                    self.assertLess(text.index('#аиставит'),text.index('Подробнее на сайте'))
                    self.assertTrue(text.endswith('📊 Подробнее на сайте 👇'))
                    self.assertNotIn('Расулов подчеркнул',text)
                    self.assertEqual(len(body.select('img')),1)
                    self.assertNotIn('horoooos.github.io',text)
            source=unescape((docs/'vk-articles/6219.html').read_text(encoding='ascii'))
            self.assertIn(tail,source)
            self.assertEqual(source.count('Расулов подчеркнул важность игры вратаря.'),70)

    def test_canonical_page_metadata_also_survives_a_legacy_decoder(self):
        title='Андреева и Шарапова — русский заголовок'
        page=pages.page('',title,'Описание новости','https://example.test/', '<p>Текст</p>',ld=[{'headline':title}])
        raw=page.encode('utf-8').decode('windows-1251',errors='replace')
        self.assertEqual(unescape(re.search('<title>(.*?)</title>',raw)[1]),title)
        self.assertEqual(unescape(re.search('property="og:title" content="([^"]+)"',raw)[1]),title)
        data=re.search('application/ld\+json">(.*?)</script>',raw)[1]
        self.assertEqual(json.loads(data)['headline'],title)
        self.assertIn('http-equiv="Content-Type" content="text/html; charset=utf-8"',page)

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
                        self.assertIn('Первый абзац.',new.findtext('description').split('\n\n#',1)[0])
                        self.assertGreater(new.findtext('description').index('Подробнее на сайте'),new.findtext('description').index('#теннис'))
                        body=unescape(new.findtext('{http://purl.org/rss/1.0/modules/content/}encoded'))
                        self.assertIn('#теннис',body)
                        self.assertIn('Заключительный абзац.',body)
                page=(docs/'vk-articles/2.html').read_bytes()
                self.assertTrue(page.isascii())
                self.assertIn('Андреева сравнили с Шараповой',unescape(page.decode('windows-1251')))

    def test_native_footer_has_one_short_source_link_and_complete_summary(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory);docs=root/'docs';images=docs/'rss-images';images.mkdir(parents=True)
            for name in ('vk_rss_since.txt','vk_rss_format_since.txt','vk_rss_ascii_since.txt','vk_rss_unified_since.txt','vk_rss_footer_since.txt'):
                (root/name).write_text('2026-11-15T00:00:00Z')
            (images/'2.jpg').write_bytes(b'jpeg')
            news=dict(id=2,title='Синнер обратился к зрителям',sport='tennis',photo='https://example.test/image.jpg',
                url='news/2.html',body='🎾 Первое завершённое предложение.\n\n'+'Полный текст новости. '*100,
                desc='Новость',complete=True,t='2026-11-15T12:00:00Z')
            def shorten(method,**params):
                return {'short_url':'https://vk.cc/source' if '/vk-articles/' in params['url'] else 'https://vk.cc/article'}
            with patch.object(pages,'DATA',root),patch.object(pages,'DOCS',docs),patch.dict(os.environ,{'VK_TOKEN':'group'}),patch('betbot.vk._call',side_effect=shorten) as api:
                for article in (False,True):
                    item=ET.fromstring(pages._vk_rss([news],pd.Timestamp('2026-11-15T13:00:00Z'),article=article)).find('channel/item')
                    self.assertEqual(item.findtext('link'),'https://vk.cc/source')
                    self.assertEqual(item.findtext('guid'),pages.SITE+'vk-articles/2.html')
                    caption=item.findtext('description')
                    self.assertTrue(caption.startswith('🎾 Первое завершённое предложение.'))
                    self.assertLessEqual(len(caption),420)
                    self.assertNotIn('vk.cc/',caption) # VK appends the one short item link.
                    self.assertGreater(caption.index('#теннис'),caption.index('предложение.'))
                    self.assertTrue(caption.endswith('📊 Подробнее на сайте 👇'))
                    wire_body=unescape(item.findtext('{http://purl.org/rss/1.0/modules/content/}encoded'))
                    self.assertEqual(wire_body.count('Полный текст новости.'),100)
                self.assertEqual(api.call_count,2) # Canonical + source URL; second feed uses cache.
            raw=(docs/'vk-articles/2.html').read_bytes()
            self.assertTrue(raw.isascii())
            self.assertIn('Синнер обратился к зрителям',unescape(raw.decode('windows-1251')))


if __name__=='__main__':unittest.main()
