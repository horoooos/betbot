import tempfile,unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import Mock,patch
import xml.etree.ElementTree as ET
import pandas as pd
from PIL import Image
from image_fixture import JPEG
from betbot import pages,vk_rss
class NewsImageGateTests(unittest.TestCase):
    def test_complete_image_bytes_required_not_extension_or_http_header(self):
        self.assertTrue(vk_rss.image_valid(JPEG))
        for data in [None,b'',b'<html>not a photo</html>'*100,JPEG[:1300]]:
            self.assertFalse(vk_rss.image_valid(data))
        b=BytesIO();Image.new('RGB',(100,100)).save(b,format='PNG')
        self.assertFalse(vk_rss.image_valid(b.getvalue()))
    def test_fake_image_content_type_and_http_errors_are_rejected(self):
        for status,content in [(200,b'<html>error</html>'*200),(404,JPEG)]:
            with patch('requests.get',return_value=Mock(status_code=status,headers={'Content-Type':'image/jpeg'},content=content)):
                self.assertFalse(vk_rss.public_image_ready('https://example.test/photo.jpg'))
        with patch('requests.get',return_value=Mock(status_code=200,headers={'Content-Type':'image/jpeg'},content=JPEG)):
            self.assertTrue(vk_rss.public_image_ready('https://example.test/photo.jpg'))
    def test_pending_cover_is_not_in_feed_and_can_return_on_retry_without_new_guid(self):
        now=pd.Timestamp('2026-11-23T18:00:00Z')
        n={'id':1,'title':'Тренер рассказал о матче','t':now.isoformat(),'sport':'football','body':'Подробности новости.','desc':'Описание','url':'news/1.html','photo':'https://example.test/source.jpg'}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);docs=root/'docs';image=docs/'rss-images/1.jpg';image.parent.mkdir(parents=True);image.write_bytes(JPEG)
            (root/'vk_rss_since.txt').write_text('2026-11-23T00:00:00Z')
            with patch.object(pages,'DATA',root),patch.object(pages,'DOCS',docs):
                with patch.object(vk_rss,'public_image_ready',return_value=False):
                    pending=ET.fromstring(pages._vk_rss([n],now));self.assertEqual(pending.findall('channel/item'),[])
                self.assertTrue((docs/'vk-articles/1.html').exists())
                with patch.object(vk_rss,'public_image_ready',return_value=True):
                    ready=ET.fromstring(pages._vk_rss([n],now));item=ready.find('channel/item')
                self.assertIsNotNone(item);self.assertEqual(item.findtext('guid'),pages.SITE+'news/1.html')
    def test_corrupt_cached_photo_is_replaced_before_feed_admission(self):
        now=pd.Timestamp('2026-11-23T18:00:00Z')
        n={'id':1,'title':'Тренер рассказал о матче','t':now.isoformat(),'sport':'football','body':'Подробности новости.','desc':'Описание','url':'news/1.html','photo':'https://example.test/source.jpg'}
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);docs=root/'docs';image=docs/'rss-images/1.jpg';image.parent.mkdir(parents=True);image.write_bytes(b'corrupt jpeg')
            (root/'vk_rss_since.txt').write_text('2026-11-23T00:00:00Z')
            with patch.object(pages,'DATA',root),patch.object(pages,'DOCS',docs),patch.object(vk_rss,'public_image_ready',return_value=True),patch('requests.get',return_value=Mock(content=JPEG)) as get:
                feed=ET.fromstring(pages._vk_rss([n],now));self.assertIsNotNone(feed.find('channel/item'))
                self.assertEqual(get.call_count,1);self.assertTrue(vk_rss.image_valid(image.read_bytes()))
    def test_native_feed_never_has_a_text_only_item(self):
        n={'id':1,'title':'Новость','t':'2026-11-23T18:00:00Z','sport':'football','body':'Текст','desc':'Текст','url':'news/1.html'}
        feed=ET.fromstring(pages._rss([n],[],{},pd.Timestamp(n['t']),feed_name='rss-vk.xml'))
        self.assertEqual(feed.findall('channel/item'),[])
