import unittest
from unittest.mock import patch
import pandas as pd
from betbot import oddspapi

class BudgetStatusTests(unittest.TestCase):
    def test_exhaustion_is_visible_and_does_not_destroy_cache_schedule(self):
        month=pd.Timestamp.now(tz=oddspapi.MSK).strftime('%Y-%m')
        state={'oddspapi':{'used':{month:oddspapi.BUDGET},'last':{'tennis':'2026-11-21T12:00:00+03:00'},'tournaments':{'tennis':[1]}}}
        with patch.object(oddspapi,'enabled',return_value=True),patch.object(oddspapi.requests,'get') as get:
            oddspapi.refresh(state)
            get.assert_not_called()
        self.assertEqual(state['oddspapi']['budget_status']['status'],'monthly_budget_exhausted')
        self.assertEqual(state['oddspapi']['last']['tennis'],'2026-11-21T12:00:00+03:00')
        self.assertEqual(state['oddspapi']['tournaments']['tennis'],[1])
    def test_new_month_has_its_own_budget_without_resetting_history(self):
        state={'oddspapi':{'used':{'2026-11':oddspapi.BUDGET}}}
        status=oddspapi.budget_status(state,pd.Timestamp('2026-12-01T00:00:00+03:00'))
        self.assertEqual(status['remaining'],oddspapi.BUDGET)
        self.assertEqual(state['oddspapi']['used']['2026-11'],oddspapi.BUDGET)
