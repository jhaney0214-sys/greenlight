"""greenlight/wishlists.py and the pairs it reads: python -m unittest tests.test_wishlists"""

import io
import os
import sys
import unittest
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import gl  # noqa: E402
from greenlight import wishlists  # noqa: E402

TRANSCRIPT = os.path.join(ROOT, "notes", "wishlists-2026-10-16.txt")


def pair(game, wishlists_, units, days, selection="own devlog", flags=None, price=None):
    return {"game": game, "wishlists": wishlists_, "units": units, "days": days,
            "selection": selection, "flags": flags or [], "price_usd": price,
            "launch": "2024-01"}


class TheDataFile(unittest.TestCase):
    """Every pair must say where it came from, and why it got published."""

    @classmethod
    def setUpClass(cls):
        cls.data = wishlists.load()

    def test_every_pair_has_a_link_a_date_and_a_quote(self):
        for p in self.data["pairs"]:
            with self.subTest(game=p["game"], days=p["days"]):
                self.assertTrue(p["source"].startswith("https://"))
                self.assertTrue(p["source_date"])
                self.assertTrue(p["quote"])
                self.assertGreater(p["wishlists"], 0)
                self.assertGreater(p["units"], 0)

    def test_every_selection_is_one_the_file_defines(self):
        kinds = set(self.data["selection_kinds"])
        for p in self.data["pairs"]:
            self.assertIn(p["selection"], kinds, p["game"])

    def test_a_figure_not_read_off_its_own_page_is_kept_out_of_the_fit(self):
        for p in self.data["pairs"]:
            self.assertIn(p["read"], ("opened", "search summary"), p["game"])
            if p["read"] != "opened":
                self.assertIn("unverified", p["flags"], p["game"])

    def test_there_are_at_least_thirty_games(self):
        self.assertGreaterEqual(len({p["game"] for p in self.data["pairs"]}), 30)

    def test_no_game_appears_twice_for_the_same_window(self):
        seen = set()
        for p in self.data["pairs"]:
            key = (p["game"], p["days"])
            self.assertNotIn(key, seen)
            seen.add(key)


class Quantile(unittest.TestCase):

    def test_interpolates_between_order_statistics(self):
        self.assertAlmostEqual(wishlists.quantile([1, 2, 3, 4], 0.5), 2.5)
        self.assertAlmostEqual(wishlists.quantile([4, 1, 3, 2], 0.25), 1.75)
        self.assertEqual(wishlists.quantile([7], 0.9), 7)

    def test_an_empty_list_is_refused(self):
        with self.assertRaises(ValueError):
            wishlists.quantile([], 0.5)


class Windows(unittest.TestCase):

    WEEK = wishlists.WINDOWS[1]

    def test_one_row_per_game_nearest_the_nominal_day(self):
        rows = wishlists.in_window([pair("A", 100, 10, 4), pair("A", 100, 30, 8),
                                    pair("A", 100, 50, 14)], self.WEEK)
        self.assertEqual([r["days"] for r in rows], [8])

    def test_flagged_undated_and_out_of_window_rows_are_left_out(self):
        rows = wishlists.in_window([pair("A", 100, 10, 7, flags=["anomaly"]),
                                    pair("B", 100, 10, None),
                                    pair("C", 100, 10, 30),
                                    pair("D", 100, 10, 7)], self.WEEK)
        self.assertEqual([r["game"] for r in rows], ["D"])


class HeldOut(unittest.TestCase):

    def test_an_outlier_falls_outside_the_range_fitted_without_it(self):
        values = [1.0] * 9 + [100.0]
        # Every 1.0 sits inside a range of nine 1.0s and one 100; the 100 does not.
        self.assertAlmostEqual(wishlists.held_out(values, 0.25, 0.75), 0.9)
        self.assertAlmostEqual(wishlists.held_out_within(values), 0.9)

    def test_too_few_values_measure_nothing(self):
        self.assertIsNone(wishlists.held_out([1.0, 2.0], 0.25, 0.75))


class Report(unittest.TestCase):

    def data(self, n):
        pairs = [pair("G%d" % i, 1000, 100 * (i + 1), 7, price=5.0) for i in range(n)]
        return {"pairs": pairs, "benchmarks": [], "year_one_multiplier": None}

    def test_states_n_and_the_held_out_error(self):
        text = wishlists.report(10000, data=self.data(10))
        self.assertIn("FIRST WEEK (4 to 14 days after launch): n = 10 games", text)
        self.assertIn("each game held out", text)
        self.assertIn("Estimated: the range for your game", text)

    def test_too_few_pairs_are_listed_not_fitted(self):
        text = wishlists.report(10000, data=self.data(wishlists.MIN_FIT - 1))
        self.assertIn("Too few pairs to fit a range", text)
        self.assertNotIn("units per wishlist   10%", text)

    def test_the_success_split_is_shown(self):
        data = self.data(10)
        for p in data["pairs"][:5]:
            p["selection"] = "success story"
        text = wishlists.report(10000, data=data)
        self.assertIn("5 of 10 were written up because they sold well", text)

    def test_a_price_band_with_few_pairs_says_so(self):
        text = wishlists.report(10000, price=20.0, data=self.data(10))
        self.assertIn("Only 0 first-week pairs state a price in this band", text)

    def test_the_real_report_labels_the_first_year_an_estimate(self):
        text = wishlists.report(20000)
        self.assertIn("FIRST YEAR - ESTIMATED, NOT MEASURED", text)
        self.assertIn("SURVEYS THAT ASKED EVERYONE", text)

    def test_the_committed_transcript_is_what_the_command_prints(self):
        # claims.json reads the README's wishlist counts off this file, so it
        # must not drift from the code and the data that produce it.
        with open(TRANSCRIPT, encoding="utf-8") as handle:
            self.assertEqual(handle.read().rstrip("\n"), wishlists.report(20000))


class Command(unittest.TestCase):

    def run_gl(self, *argv):
        out = io.StringIO()
        with redirect_stdout(out):
            code = gl.main(list(argv))
        return code, out.getvalue()

    def test_prints_the_report(self):
        code, text = self.run_gl("wishlists", "20000")
        self.assertEqual(code, 0)
        self.assertIn("WISHLISTS TO SALES - 20,000 wishlists at launch", text)

    def test_refuses_a_non_positive_wishlist_count(self):
        code, text = self.run_gl("wishlists", "0")
        self.assertEqual(code, 1)
        self.assertIn("positive", text)


if __name__ == "__main__":
    unittest.main()
