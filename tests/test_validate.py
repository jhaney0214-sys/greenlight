"""tools/validate.py, without the network: python -m unittest tests.test_validate

The rows below are made up in the survey's shape. The survey itself is
GameDiscoverCo's and is not in this repository.
"""

import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tools"))

import validate  # noqa: E402
from greenlight import revenue  # noqa: E402

SHEET = '''"GameDiscoverCo - Steam 'reviews to sales' ratio, Oct. 2022 2",,,
Which year did this game launch on Steam?,This game is currently...,How many reviews?,Lifetime Steam units?
Before 2016,,1000,70000
2022,Early Access,100,3000
2022,Free To Play,7640,1149216
2021,,"1,200",42000
2020,,,5000
2019,,0,10
'''


class Parse(unittest.TestCase):

    def test_headers_blanks_and_free_games_are_left_out(self):
        self.assertEqual(validate.parse(SHEET),
                         [(2015, "", 1000, 70000),
                          (2022, "Early Access", 100, 3000),
                          (2021, "", 1200, 42000)])


class Errors(unittest.TestCase):

    def test_an_exact_estimate_is_one(self):
        year = 2022
        game = (year, "", 100, int(100 * revenue.review_multiplier(year)))
        self.assertAlmostEqual(validate.errors([game])[0], 1.0)

    def test_a_game_that_sold_twice_the_estimate_is_a_half(self):
        year = 2022
        game = (year, "", 100, int(200 * revenue.review_multiplier(year)))
        self.assertAlmostEqual(validate.errors([game])[0], 0.5)


class Summary(unittest.TestCase):

    def game(self, factor):
        """A 2022 game that really sold `factor` times what is estimated."""
        return (2022, "", 100, int(100 * revenue.review_multiplier(2022) * factor))

    def test_inside_the_range_means_the_real_figure_is_between_low_and_high(self):
        spread = revenue.MULTIPLIER_SPREAD
        s = validate.summary([self.game(1.0), self.game(1 - spread + 0.01),
                              self.game(1 + spread - 0.01), self.game(1 + spread + 0.2),
                              self.game(0.3)])
        self.assertAlmostEqual(s["inside_range"], 3 / 5)

    def test_the_interval_holds_the_share_it_is_asked_for(self):
        # Real copies at 0.1x, 0.2x ... 10x the estimate (101 games, evenly in log).
        factors = [10 ** (i / 50 - 1) for i in range(101)]
        games = [self.game(f) for f in factors]
        low, high = validate.interval(games, 0.8)
        held = sum(1 for f in factors if low <= f <= high) / len(factors)
        self.assertAlmostEqual(held, 0.8, delta=0.03)
        self.assertLess(low, 1.0)
        self.assertGreater(high, 1.0)

    def test_too_few_games_give_no_interval(self):
        self.assertIsNone(validate.interval([self.game(1.0)] * 9))

    def test_an_empty_group_has_no_summary(self):
        self.assertIsNone(validate.summary([]))

    def test_the_report_names_every_group_that_has_games(self):
        text = validate.report(validate.parse(SHEET))
        self.assertIn("every paid game", text)
        self.assertIn("in Early Access", text)
        self.assertNotIn("released 2016-2019", text)


if __name__ == "__main__":
    unittest.main()
