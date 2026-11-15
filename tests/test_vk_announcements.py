import unittest
from html import unescape
from html.parser import HTMLParser

from betbot import vk_rss


class TextReader(HTMLParser):
    def __init__(self):
        super().__init__();self.parts=[]
    def handle_data(self,data):self.parts.append(data)


class VKAnnouncementTests(unittest.TestCase):
    def news(self,body):
        return dict(title='Team Spirit потерпел разгром в финале',sport='esports',photo='https://example.test/image.jpg',
                    rss_link='https://vk.cc/example',body=body)

    def test_wall_announcement_finishes_a_paragraph_before_long_continuation(self):
        first='📰 Team Spirit уступил сопернику в финале. Итог встречи — 0:3.'
        later='🔥 Публика и зрители обсуждали завершившуюся встречу. '*30
        n=self.news(first+'\n\n'+later+'\n\n#киберспорт\n\n📊 Подробнее на сайте 👉 vk.cc/example')
        teaser=vk_rss.announcement(n)
        self.assertLessEqual(len(teaser),420)
        self.assertTrue(teaser.startswith(first))
        self.assertEqual(teaser.count('vk.cc/example'),1)
        self.assertNotIn('Публика и',teaser)
        self.assertIn('#киберспорт',teaser)

    def test_long_first_paragraph_stops_at_complete_sentences(self):
        n=self.news('Первое законченное предложение. '+('Следующее законченное предложение. '*50))
        teaser=vk_rss.announcement(n)
        self.assertLessEqual(len(teaser),420)
        self.assertTrue(teaser.split('\n\n#',1)[0].endswith('предложение.'))
        self.assertIn('Первое законченное предложение.',teaser)
        self.assertNotIn('…',teaser)

    def test_no_slicing_a_single_oversized_sentence(self):
        n=self.news('Оченьдлинныйтекстбезточек '*100)
        teaser=vk_rss.announcement(n)
        self.assertTrue(teaser.startswith('Полный материал и подробности — в статье.'))
        self.assertNotIn('Оченьдлинный',teaser.split('\n\n#',1)[0])

    def test_complete_article_keeps_last_paragraph_even_with_a_short_teaser(self):
        end='Заключительный абзац, который остаётся внутри полной статьи.'
        n=self.news(('Большой первый абзац. '*100)+'\n\n'+end)
        html=vk_rss.article_page(n)
        reader=TextReader();reader.feed(html)
        self.assertIn(end,''.join(reader.parts))
        self.assertNotIn(end,vk_rss.announcement(n))
        # Metadata carries the compact teaser, not a sliced full article.
        self.assertIn('content="'+vk_rss.announcement(n).encode('ascii','xmlcharrefreplace').decode('ascii'),html)


if __name__=='__main__':unittest.main()
