import unittest
from datetime import datetime
from planner import TAIPEI, choose_plan, next_saturday


class PlannerTests(unittest.TestCase):
    def test_next_week_in_taiwan(self):
        self.assertEqual(str(next_saturday(datetime(2026,10,24,23,50,tzinfo=TAIPEI))), '2026-10-31')

    def test_common_court_preferred_over_cheaper_split(self):
        rows = [dict(hour=h, court=c, price=p, available=True) for h,c,p in
                [(15,'匹克1',100),(16,'匹克2',100),(15,'匹克3',450),(16,'匹克3',450)]]
        self.assertEqual([r['court'] for r in choose_plan(rows)], ['匹克3','匹克3'])

    def test_no_partial_or_over_budget(self):
        self.assertIsNone(choose_plan([dict(hour=15,court='匹克1',price=450,available=True)]))
        self.assertIsNone(choose_plan([dict(hour=h,court='匹克1',price=500,available=True) for h in (15,16)]))

    def test_booked_court_is_not_selected(self):
        self.assertIsNone(choose_plan([dict(hour=h,court='匹克1',price=450,available=h==15) for h in (15,16)]))


if __name__ == '__main__':
    unittest.main()
