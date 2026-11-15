import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock,patch
import pandas as pd
from betbot import vk_rss_audit as audit,vk


class NativeRSSAuditTests(unittest.TestCase):
    def item(self):return dict(title='Тест оформления',description='Первый абзац закончен.\n\n#футбол #аиставит\n\n📊 Подробнее на сайте 👇')
    def post(self):return dict(id=123,text='Тест оформления\n\n'+self.item()['description']+'\nvk.cc/example',attachments=[dict(type='article',article=dict(title='Тест оформления',photo={'id':1}))])

    def test_real_complete_caption_is_verified_and_clipped_full_text_fails(self):
        self.assertEqual(audit.inspect(self.post(),[self.item()])['status'],'verified')
        clipped={**self.post(),'text':'Тест оформления\n\nПервый абзац закончен. Длинный текст обрывае\nvk.cc/example'}
        receipt=audit.inspect(clipped,[self.item()])
        self.assertEqual(receipt['status'],'needs_review')
        self.assertFalse(receipt['checks']['expected_caption_present'])
        self.assertFalse(receipt['checks']['hashtags_present'])
        trailing={**self.post(),'text':self.post()['text']+' Лишний текст снова обрывае'}
        self.assertFalse(audit.inspect(trailing,[self.item()])['checks']['complete_layout'])
        self.assertIsNone(audit.inspect({'text':'Другая новость'},[self.item()]))

    def test_cursor_survives_runs_without_persisting_access_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            feed=Path(tmp)/'rss.xml';feed.write_text('<rss><channel><item><title>Тест оформления</title><description>Первый абзац закончен.\n\n#футбол #аиставит\n\n📊 Подробнее на сайте 👇</description></item></channel></rss>',encoding='utf-8')
            response=Mock();response.json.return_value={'ts':'11','updates':[dict(type='wall_post_new',group_id=vk.GROUP_ID,object=self.post())]}
            state={};server=dict(server='https://example.test/poll',key='sensitive-value',ts='10')
            with patch.object(audit,'FEED',feed),patch.dict(os.environ,{'VK_TOKEN':'token'}),patch.object(vk,'_call',return_value=server),patch.object(audit.requests,'get',return_value=response) as get:
                audit.poll(state,pd.Timestamp('2026-11-15T19:00:00Z'))
                response.json.return_value={'ts':'12','updates':[]}
                audit.poll(state,pd.Timestamp('2026-11-15T19:02:00Z'))
                self.assertEqual(get.call_args.kwargs['params']['ts'],'11')
            self.assertEqual(state['vk_rss_audit']['posts'][0]['status'],'verified')
            self.assertNotIn('sensitive-value',str(state));self.assertNotIn('key',state['vk_rss_audit'])
