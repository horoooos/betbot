import json
import unittest
from unittest.mock import Mock, patch
from types import SimpleNamespace
from betbot.broadcasts import public_video, panda_streams, title_matches, youtube_listing, espn_streams, live_title_teams


class BroadcastTests(unittest.TestCase):
    def test_public_urls_canonical_and_not_private_or_embeds(self):
        self.assertEqual(public_video('https://twitch.tv/esl_dota2?token=secret')['url'], 'https://www.twitch.tv/esl_dota2')
        self.assertEqual(public_video('https://youtu.be/abcdefghijk?t=2')['video_id'], 'abcdefghijk')
        for url in ['http://twitch.tv/esl', 'https://twitch.tv.evil/x', 'https://twitch.tv/videos/42',
                    'https://user:pass@twitch.tv/esl', 'https://twitch.tv:443/esl', 'https://youtube.com/embed/abcdefghijk']:
            self.assertIsNone(public_video(url), url)

    def test_event_metadata_dedupes_without_claiming_live(self):
        streams = panda_streams({'streams_list': [{'raw_url': 'https://twitch.tv/esl_dota2', 'language': 'ru'}],
                                 'official_stream_url': 'https://twitch.tv/esl_dota2',
                                 'english': {'embed_url': '<iframe>unsafe</iframe>'}})
        self.assertEqual(len(streams), 1)
        self.assertEqual(streams[0]['status'], 'listed')
        self.assertEqual(streams[0]['access'], 'unknown')

    def test_match_both_names_not_substrings_or_highlights(self):
        names = [['Team Spirit', 'Spirit'], ['PARIVISION']]
        self.assertTrue(title_matches('LIVE: PARIVISION vs Team Spirit | Dota 2', names))
        self.assertFalse(title_matches('Team Spirit vs Aurora', names))
        self.assertFalse(title_matches('Team Spirit vs PARIVISION Highlights', names))
        self.assertFalse(title_matches('Team Spirits vs PARIVISION', [['Team Spirit'], ['PARIVISION']]))
        self.assertFalse(title_matches('LGD vs OG', [['LGD'], ['OG']]))

    def test_youtube_actual_live_badge_not_title(self):
        def page(items):
            return 'var ytInitialData = ' + json.dumps({'contents': items}) + ';'
        live = {'videoRenderer': {'videoId': 'abcdefghijk', 'title': {'runs': [{'text': 'Match'}]},
                                 'thumbnailOverlays': [{'thumbnailOverlayTimeStatusRenderer': {'style': 'LIVE'}}]}}
        replay = {'videoRenderer': {'videoId': '12345678901', 'title': {'runs': [{'text': 'LIVE match'}]}}}
        upcoming = {'lockupViewModel': {'contentId': '12345678902', 'contentImage': {
            'thumbnailViewModel': {'overlays': [{'text': 'Upcoming'}]}}, 'metadata': {}}}
        self.assertEqual([v['video_id'] for v in youtube_listing(page([live, replay, upcoming]))], ['abcdefghijk'])

    def test_discovered_match_does_not_need_a_prediction(self):
        self.assertEqual(live_title_teams('LIVE - Cuba vs Grenada | Concacaf'), ['Cuba', 'Grenada'])
        self.assertIsNone(live_title_teams('DreamLeague live studio'))
        self.assertIsNone(live_title_teams('RERUN: Cuba vs Grenada'))

    def test_publish_preserves_other_rules_when_etag_unavailable(self):
        from tools.broadcast_scan import publish
        session = Mock()
        session.get.return_value.headers = {}
        session.get.return_value.json.return_value = {'rules': {'private': {'.read': False}}}
        module = SimpleNamespace(admin_session=lambda: session, DB='https://example.invalid')
        with patch.dict('sys.modules', {'dota_live_relay': module}):
            publish({'at': 100, 'matches': []})
        rules_call = session.put.call_args_list[0]
        self.assertEqual(rules_call.kwargs['json']['rules']['private'], {'.read': False})
        self.assertEqual(rules_call.kwargs['json']['rules']['broadcasts'], {'.read': True, '.write': False})
        self.assertEqual(session.put.call_count, 2)

    def test_espn_does_not_offer_highlights_or_tracking_tokens(self):
        raw = {'videos': [{'links': [{'rel': ['watch'], 'href': 'https://www.espn.com/watch/player?id=clip'}]}],
               'header': {'links': [{'rel': ['watch'], 'href': 'https://www.espn.com/watch/player?id=public-id&token=private'},
                                    {'rel': ['summary'], 'href': 'https://www.espn.com/watch/player?id=no'},
                                    {'rel': ['watch'], 'href': 'https://evil.test/watch/player?id=no'}]}}
        streams = espn_streams(raw)
        self.assertEqual(len(streams), 1)
        self.assertEqual(streams[0]['url'], 'https://www.espn.com/watch/player?id=public-id')
        self.assertEqual(streams[0]['access'], 'unknown')


if __name__ == '__main__':
    unittest.main()
