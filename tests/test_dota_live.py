import copy
import unittest
from tools.dota_live_relay import snapshot


class DotaLiveTests(unittest.TestCase):
    def frame(self):
        return {'match': {'match_id': 123, 'game_time': 42}, 'teams': [
            {'team_number': team, 'team_name': str(team), 'players': [
                {'playerid': i, 'x': .01*i, 'y': -.2, 'heroid': i+1} for i in range(5)]}
            for team in (2, 3)]}

    def test_real_positions_preserved_including_negative_coordinates(self):
        frame = self.frame()
        out = snapshot(frame, 100)
        self.assertEqual(out['teams'][0]['players'][0]['y'], -.2)
        self.assertEqual(out['match_id'], '123')
        self.assertEqual(out['at'], 100)
        self.assertEqual(len(out['teams'][1]['players']), 5)

    def test_missing_or_prestart_frames_are_not_invented(self):
        for value in (None, {}, {'teams': None}):
            self.assertIsNone(snapshot(value))
        frame = self.frame()
        for team in frame['teams']:
            for player in team['players']:
                player.update(x=0, y=0)
        self.assertIsNone(snapshot(frame))
        frame['teams'][0]['players'].pop()
        self.assertIsNone(snapshot(frame))

    def test_nonfinite_positions_rejected(self):
        frame = self.frame()
        frame['teams'][0]['players'][0]['x'] = float('nan')
        with self.assertRaises(ValueError):
            snapshot(frame)
