import unittest,json
from unittest.mock import patch,Mock
import pandas as pd
from betbot import promotion,content

class PromotionTests(unittest.TestCase):
    def test_buttons_are_owned_navigation_and_user_initiated_share(self):
        keyboard=json.loads(promotion.news_keyboard(123))
        urls=[b['url'] for row in keyboard['inline_keyboard'] for b in row]
        self.assertTrue(all(u.startswith(('https://horoooos.github.io/betbot/','https://t.me/share/url?')) for u in urls))
        self.assertIn('aistavvit',urls[-1])
    def test_weekly_invite_is_checkpointed_before_send_and_not_repeated(self):
        now=pd.Timestamp('2026-11-22T17:00:00+03:00');state={};saved=[]
        def checkpoint():saved.append(state['promotion']['status'])
        with patch('betbot.content.invite',return_value=123) as send:
            self.assertTrue(promotion.run(state,now,pd.DataFrame(),'brand',checkpoint))
            self.assertFalse(promotion.run(state,now+pd.Timedelta(minutes=2),pd.DataFrame(),'brand',checkpoint))
            self.assertFalse(promotion.run(state,now+pd.Timedelta(days=1),pd.DataFrame(),'brand',checkpoint))
            self.assertEqual(send.call_count,1)
        self.assertEqual(saved[0],'sending');self.assertEqual(state['promotion']['status'],'published')
    def test_unknown_delivery_outcome_does_not_repeat_a_campaign(self):
        now=pd.Timestamp('2026-11-22T17:00:00+03:00');state={}
        with patch('betbot.content.invite',side_effect=RuntimeError('timeout')) as send:
            self.assertFalse(promotion.run(state,now,pd.DataFrame(),'brand'))
            self.assertFalse(promotion.run(state,now,pd.DataFrame(),'brand'))
            self.assertEqual(send.call_count,1)
    def test_invite_does_not_present_win_rate_as_profit(self):
        res=pd.DataFrame({'main_hit':[True]*6+[False]*4,'main_odds':[1.5]*10,'main_est':[False]*10})
        with patch('betbot.card.invite_card',return_value=b'image'),patch.object(content,'_post',return_value=1) as post:
            content.invite(res,'brand')
            text=post.call_args.args[1]
        self.assertIn('-10.0%',text);self.assertIn('Проходимость не равна прибыли',text)
