"""Tests for gl.py features.

The point of the command is that it compares winners with losers on a sample
that holds both. The tests that matter most are the ones that would fail if a
feature carried by every game, winners and losers alike, came out looking like
a reason to build it.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from greenlight import collect, features, revenue  # noqa: E402


def app(reviews, categories=(), tags=None, name="Game", year=2022, price=1499, **extra):
    record = {
        "appid": abs(hash((name, reviews))) % 10 ** 6,
        "name": name,
        "total_reviews": reviews,
        "positive": int(reviews * 0.8),
        "negative": reviews - int(reviews * 0.8),
        "price_cents": price,
        "is_free": price == 0,
        "release_year": year,
        "categories": list(categories),
        "tags": tags or {},
    }
    record.update(extra)
    record["estimate"] = revenue.estimate(record)
    return record


def niche_of(winner_feature, n=12):
    big = [app(5000 + i, ["Co-op", "Single-player"], name="Big %d" % i) for i in range(n)]
    small = [app(40 + i, ["Single-player"], name="Small %d" % i) for i in range(n)]
    return big + small


class TestCompare(unittest.TestCase):

    def test_a_feature_only_the_winners_carry_reads_higher(self):
        rows = {r["feature"]: r for r in features.compare(niche_of("Co-op"), boots=200)}
        self.assertEqual(rows["cat: Co-op"]["reading"], "higher")
        self.assertGreater(rows["cat: Co-op"]["lo"], 1)
        self.assertEqual(rows["cat: Co-op"]["top_share"], 1.0)
        self.assertEqual(rows["cat: Co-op"]["bottom_share"], 0.0)

    def test_a_feature_every_game_carries_is_not_compared(self):
        # Single-player is on winners and losers alike; there is no "without"
        # group, so it must not appear as a finding at all.
        rows = {r["feature"] for r in features.compare(niche_of("Co-op"), boots=200)}
        self.assertNotIn("cat: Single-player", rows)

    def test_a_feature_split_evenly_shows_no_clear_difference(self):
        apps = []
        for i in range(12):
            apps.append(app(5000 + i, ["Even"] if i % 2 else [], name="Big %d" % i))
            apps.append(app(40 + i, ["Even"] if i % 2 else [], name="Small %d" % i))
        rows = {r["feature"]: r for r in features.compare(apps, boots=200)}
        self.assertEqual(rows["cat: Even"]["reading"], "no clear difference")

    def test_too_few_games_with_a_feature_is_dropped(self):
        apps = niche_of("Co-op")
        apps[0]["categories"].append("Rare")
        rows = {r["feature"] for r in features.compare(apps, min_n=8, boots=50)}
        self.assertNotIn("cat: Rare", rows)

    def test_earned_features_are_marked(self):
        apps = [app(5000 + i, ["Steam Trading Cards"], name="B%d" % i) for i in range(10)]
        apps += [app(40 + i, [], name="S%d" % i) for i in range(10)]
        rows = {r["feature"]: r for r in features.compare(apps, boots=50)}
        self.assertTrue(rows["cat: Steam Trading Cards"]["earned"])

    def test_free_games_are_left_out(self):
        apps = niche_of("Co-op") + [app(90000, ["Co-op"], name="F2P", price=0)]
        rows = {r["feature"]: r for r in features.compare(apps, boots=50)}
        self.assertEqual(rows["cat: Co-op"]["n_with"], 12)

    def test_the_bootstrap_is_seeded(self):
        a = features.compare(niche_of("Co-op"), boots=100, seed=3)
        b = features.compare(niche_of("Co-op"), boots=100, seed=3)
        self.assertEqual(a, b)

    def test_too_small_a_sample_gives_nothing(self):
        self.assertEqual(features.compare(niche_of("Co-op", n=3)), [])


class TestFeaturesOf(unittest.TestCase):

    def test_store_fields_become_labels(self):
        got = features.features_of({
            "categories": ["Steam Workshop"], "controller": "partial",
            "platforms": ["windows", "linux"], "languages": 6,
            "early_access": True, "dlc_count": 2, "tags": {"Puzzle": 30}})
        self.assertEqual(got, {
            "cat: Steam Workshop", "runs on linux",
            "5+ languages", "Early Access on the store page", "has DLC",
            "tag: Puzzle"})

    def test_an_empty_record_has_no_features(self):
        self.assertEqual(features.features_of({}), set())


class TestLanguageCount(unittest.TestCase):

    def test_steam_markup_and_footnote(self):
        raw = ("English<strong>*</strong>, French, German<strong>*</strong>"
               "<br><strong>*</strong>languages with full audio support")
        self.assertEqual(collect.language_count(raw), 3)

    def test_nothing_listed(self):
        self.assertIsNone(collect.language_count(""))
        self.assertIsNone(collect.language_count(None))


class TestAsks(unittest.TestCase):

    def review(self, text, rid="1", up=True, votes=3):
        return {"recommendationid": rid, "review": text, "voted_up": up,
                "votes_up": votes, "timestamp_created": 1,
                "author": {"steamid": "765", "playtime_forever": 600}}

    def test_a_wish_is_found_and_linked(self):
        asks = features.extract_asks(
            [self.review("Great physics. I wish there was a level editor! 10/10")], 42, "G")
        self.assertEqual(len(asks), 1)
        self.assertEqual(asks[0]["text"], "I wish there was a level editor!")
        self.assertEqual(asks[0]["hours"], 10)
        self.assertEqual(asks[0]["url"],
                         "https://steamcommunity.com/profiles/765/recommended/42/")

    def test_praise_alone_is_not_an_ask(self):
        self.assertEqual(features.extract_asks(
            [self.review("Great physics and a lovely soundtrack.")], 42, "G"), [])

    def test_steam_markup_is_stripped(self):
        asks = features.extract_asks(
            [self.review("[h1]Verdict[/h1] It really needs more levels.")], 1, "G")
        self.assertEqual(asks[0]["text"], "Verdict It really needs more levels.")

    def test_themes_count_reviews_not_mentions(self):
        asks = (features.extract_asks([self.review("I wish multiplayer. Needs more multiplayer.", "1")], 1, "A")
                + features.extract_asks([self.review("I wish it had multiplayer.", "2")], 2, "B"))
        words = {w["word"]: w for w in features.themes(asks)}
        self.assertEqual(words["multiplayer"]["reviews"], 2)
        self.assertEqual(words["multiplayer"]["games"], 2)
        self.assertNotIn("wish", words)


if __name__ == "__main__":
    unittest.main()
