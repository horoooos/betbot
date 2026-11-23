import unittest
from html.parser import HTMLParser
from betbot import pages
import pandas as pd

class VisibleText(HTMLParser):
    def __init__(self):super().__init__();self.hidden=0;self.text=[]
    def handle_starttag(self,tag,attrs):
        if tag in ('style','script','head'):self.hidden+=1
    def handle_endtag(self,tag):
        if tag in ('style','script','head'):self.hidden=max(0,self.hidden-1)
    def handle_data(self,data):
        if not self.hidden:self.text.append(data)

class NewsLayoutTests(unittest.TestCase):
    def test_news_archive_does_not_print_css_as_article_text(self):
        now=pd.Timestamp('2026-11-23T10:00:00Z')
        news=[{'id':i,'sport':'football','title':f'Спортивная новость {i}','t':now,'body':'Новость.','desc':'Описание','photo':None,'url':f'news/{i}.html'} for i in range(20)]
        parser=VisibleText();parser.feed(pages._news_index(news));text=' '.join(parser.text)
        self.assertIn('Архив новостей',text)
        for css in ('@media','overflow-wrap','grid-template-columns','аккуратные переносы'):
            self.assertNotIn(css,text)
