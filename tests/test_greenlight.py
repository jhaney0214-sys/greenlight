"""Tests for Greenlight.

The two that matter most are the junk-tag guard and the population/sample split.
Both cover the same failure: a number that looks authoritative and is quietly
about something else. SteamSpy answers an unknown tag with a fixed list of
unrelated games rather than an error, and ranking a niche by review count before
taking a median makes the median game come out as Age of Empires II.
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from greenlight import analyze, collect, render, revenue, sources, store  # noqa: E402


def app(reviews=100, price=1999, year=2022, tags=None, name="Game", owners=None):
    record = {
        "appid": abs(hash((name, reviews, price))) % 10 ** 6,
        "name": name,
        "total_reviews": reviews,
        "positive": int(reviews * 0.8),
        "negative": reviews - int(reviews * 0.8),
        "price_cents": price,
        "is_free": price == 0,
        "release_year": year,
        "tags": tags or {},
        "owners": owners,
    }
    record["estimate"] = revenue.estimate(record)
    record["confidence"] = revenue.confidence(record, record["estimate"])
    return record


class TestJunkTagGuard(unittest.TestCase):
    """SteamSpy returns junk rather than an error for a tag that does not exist."""

    def junk(self):
        payload = {str(i): {"name": "Filler %d" % i} for i in range(1, 70)}
        payload["0"] = {"name": "Grand Theft Auto IV: Complete Edition"}
        return payload

    def test_the_fingerprint_is_recognised(self):
        self.assertTrue(sources.looks_like_junk_tag(self.junk()))

    def test_a_real_payload_is_not_flagged(self):
        real = {str(i): {"name": "Real Game %d" % i} for i in range(300)}
        self.assertFalse(sources.looks_like_junk_tag(real))

    def test_seventy_real_apps_are_not_flagged(self):
        # The size alone must not condemn a payload - only size plus the marker.
        payload = {str(i): {"name": "Real Game %d" % i} for i in range(70)}
        self.assertFalse(sources.looks_like_junk_tag(payload))

    def test_junk_becomes_an_exception_not_a_result(self):
        class FakeCache:
            def __init__(self, payload):
                self.payload = payload
                self.forgotten = []

            def get(self, url, max_age):
                return self.payload

            def put(self, url, value):
                pass

            def forget(self, url):
                self.forgotten.append(url)

        cache = FakeCache(self.junk())
        with self.assertRaises(sources.UnknownTag):
            sources.tag("Drones", cache=cache)
        # And the junk must not be left in the cache to be served again.
        self.assertTrue(cache.forgotten)

    def test_an_empty_payload_is_also_an_unknown_tag(self):
        # REGRESSION: SteamSpy has two ways of saying "no such tag" and only one
        # was handled. "Real Time Strategy" returns nothing at all, and that
        # reported cleanly as "0 apps" - a silent nothing is the same failure as
        # a silent something.
        class EmptyCache:
            def get(self, url, max_age):
                return {}

            def put(self, url, value):
                pass

            def forget(self, url):
                pass

        with self.assertRaises(sources.UnknownTag):
            sources.tag("Real Time Strategy", cache=EmptyCache())

    def test_empty_and_malformed_payloads_are_safe(self):
        self.assertFalse(sources.looks_like_junk_tag({}))
        self.assertFalse(sources.looks_like_junk_tag(None))
        self.assertFalse(sources.looks_like_junk_tag([1, 2, 3]))


class TestReleaseYear(unittest.TestCase):

    def test_full_date(self):
        self.assertEqual(collect.release_year("Oct 28, 2021"), 2021)

    def test_year_only(self):
        self.assertEqual(collect.release_year("2019"), 2019)

    def test_quarter(self):
        self.assertEqual(collect.release_year("Q4 2024"), 2024)

    def test_unreleased_text(self):
        self.assertIsNone(collect.release_year("Coming soon"))

    def test_absent(self):
        self.assertIsNone(collect.release_year(None))
        self.assertIsNone(collect.release_year(""))

    def test_implausible_year_is_refused(self):
        self.assertIsNone(collect.release_year("Jan 1, 1899"))


class TestRevenueModel(unittest.TestCase):

    def test_multiplier_falls_over_time(self):
        self.assertGreater(revenue.review_multiplier(2012),
                           revenue.review_multiplier(2024))

    def test_unknown_year_gets_a_middling_multiplier(self):
        m = revenue.review_multiplier(None)
        self.assertTrue(25 <= m <= 70)

    def test_no_reviews_means_no_estimate(self):
        self.assertIsNone(revenue.estimate_sales(0, 2022))
        self.assertFalse(revenue.estimate(app(reviews=0))["known"])

    def test_estimate_brackets_the_midpoint(self):
        low, mid, high = revenue.estimate_sales(1000, 2022)
        self.assertLess(low, mid)
        self.assertLess(mid, high)

    def test_free_games_earn_nothing_from_price(self):
        self.assertEqual(revenue.net_revenue(10000, 0), 0.0)

    def test_owners_band_parses(self):
        self.assertEqual(revenue.owners_band("2,000,000 .. 5,000,000"),
                         (2000000, 5000000))

    def test_owners_band_rejects_junk(self):
        self.assertIsNone(revenue.owners_band("0"))
        self.assertIsNone(revenue.owners_band(None))
        self.assertIsNone(revenue.owners_band("lots"))

    def test_thin_review_counts_are_marked_poor(self):
        record = app(reviews=12)
        self.assertEqual(revenue.confidence(record, record["estimate"]), "poor")

    def test_disagreeing_estimates_are_marked_fair(self):
        # SteamSpy says a million owners; reviews imply about 3,500 sales.
        record = app(reviews=100, owners="1,000,000 .. 2,000,000")
        self.assertEqual(revenue.confidence(record, record["estimate"]), "fair")

    def test_agreeing_estimates_are_marked_good(self):
        record = app(reviews=1000, owners="20,000 .. 50,000")
        self.assertEqual(revenue.confidence(record, record["estimate"]), "good")


class TestDistribution(unittest.TestCase):
    """Percentiles, never averages - Steam revenue is a power law."""

    def skewed(self):
        # One breakout, a few middling, many failures. The real shape.
        return ([app(reviews=200000, name="Breakout")]
                + [app(reviews=2000, name="Mid %d" % i) for i in range(5)]
                + [app(reviews=20, name="Flop %d" % i) for i in range(40)])

    def test_median_reflects_the_floor_not_the_breakout(self):
        dist = analyze.revenue_distribution(self.skewed())
        self.assertLess(dist["median"], dist["max"] / 100.0)

    def test_concentration_is_reported(self):
        dist = analyze.revenue_distribution(self.skewed())
        self.assertGreater(dist["top_decile_share"], 0.5)

    def test_failure_counts_are_reported(self):
        dist = analyze.revenue_distribution(self.skewed())
        self.assertGreater(dist["under_10k"], 30)

    def test_free_games_are_left_out_of_revenue(self):
        apps = [app(price=0, name="Free"), app(price=1999, name="Paid")]
        self.assertEqual(analyze.revenue_distribution(apps)["n"], 1)

    def test_empty_input_is_harmless(self):
        self.assertEqual(analyze.revenue_distribution([])["n"], 0)

    def test_percentile_edges(self):
        self.assertIsNone(analyze.percentile([], 0.5))
        self.assertEqual(analyze.percentile([5], 0.5), 5)
        self.assertEqual(analyze.percentile([1, 2, 3], 0.0), 1)
        self.assertEqual(analyze.percentile([1, 2, 3], 1.0), 3)


class TestPopulationVersusSample(unittest.TestCase):
    """REGRESSION: the first version ranked by reviews and then took a median.

    That made the median game in a niche of hundreds come out as Age of Empires
    II at an estimated $110M. The revenue distribution must be computed over the
    whole population; only tag and cadence analysis may use the biased top slice.
    """

    def test_population_record_needs_no_extra_requests(self):
        record = collect.population_record("42", {
            "name": "Thing", "positive": 800, "negative": 200,
            "initialprice": "1999", "owners": "20,000 .. 50,000"})
        self.assertEqual(record["total_reviews"], 1000)
        self.assertEqual(record["price_cents"], 1999)
        self.assertFalse(record["is_free"])

    def test_population_record_handles_missing_price(self):
        record = collect.population_record("42", {"name": "T", "positive": 5,
                                                  "negative": 5})
        self.assertEqual(record["price_cents"], 0)
        self.assertTrue(record["is_free"])

    def test_top_slice_median_is_far_above_the_population_median(self):
        # Ten hits and a hundred flops, which is roughly the real shape.
        population = ([app(reviews=200000, name="Huge %d" % i) for i in range(10)]
                      + [app(reviews=30, name="Small %d" % i) for i in range(100)])
        top_slice = sorted(population,
                           key=lambda a: a["total_reviews"], reverse=True)[:10]
        self.assertGreater(analyze.revenue_distribution(top_slice)["median"],
                           analyze.revenue_distribution(population)["median"] * 50)

    def test_summarise_reports_both_sizes_separately(self):
        population = [app(reviews=100, name="P%d" % i) for i in range(50)]
        sample = population[:10]
        summary = analyze.summarise(population, sample, {"name": "n"})
        self.assertEqual(summary["population"], 50)
        self.assertEqual(summary["sample"], 10)
        self.assertEqual(summary["revenue"]["n"], 50)


class TestTagPerformance(unittest.TestCase):

    def test_a_tag_on_the_winners_outscores_one_on_the_losers(self):
        apps = ([app(reviews=50000, tags={"Co-op": 100}, name="Big %d" % i)
                 for i in range(5)]
                + [app(reviews=100, tags={"Solo": 100}, name="Small %d" % i)
                   for i in range(5)])
        rows = {r["tag"]: r for r in analyze.tag_performance(apps)}
        self.assertGreater(rows["Co-op"]["vs_niche"], rows["Solo"]["vs_niche"])
        self.assertGreater(rows["Co-op"]["vs_niche"], 1.0)

    def test_rare_tags_are_dropped(self):
        apps = [app(tags={"Rare": 1}, name="Only one")] + [
            app(tags={"Common": 1}, name="C%d" % i) for i in range(6)]
        tags = {r["tag"] for r in analyze.tag_performance(apps, min_apps=4)}
        self.assertNotIn("Rare", tags)

    def test_required_tags_are_excluded_as_uninformative(self):
        apps = [app(tags={"RTS": 1, "Co-op": 1}, name="G%d" % i) for i in range(6)]
        tags = {r["tag"] for r in analyze.tag_performance(apps, exclude=["RTS"])}
        self.assertNotIn("RTS", tags)
        self.assertIn("Co-op", tags)


class TestNicheFiltering(unittest.TestCase):

    def test_unreleased_games_are_dropped(self):
        record = dict(app(), coming_soon=True)
        ok, why = collect.keeps(record, {})
        self.assertFalse(ok)
        self.assertEqual(why, "unreleased")

    def test_dlc_is_dropped(self):
        ok, why = collect.keeps(None, {})
        self.assertFalse(ok)

    def test_excluded_tag_drops_a_game(self):
        record = app(tags={"Anime": 50})
        ok, _why = collect.keeps(record, {"exclude_tags": ["Anime"]})
        self.assertFalse(ok)

    def test_theme_filter_requires_one_match(self):
        record = app(tags={"Medieval": 10})
        ok, _ = collect.keeps(record, {"any_tags": ["Modern", "Military"]})
        self.assertFalse(ok)
        record = app(tags={"Military": 10})
        ok, _ = collect.keeps(record, {"any_tags": ["Modern", "Military"]})
        self.assertTrue(ok)

    def test_release_cutoff(self):
        ok, _ = collect.keeps(app(year=2012), {"released_since": 2016})
        self.assertFalse(ok)


class TestCache(unittest.TestCase):

    def setUp(self):
        self.cache = store.Cache(os.path.join(tempfile.mkdtemp(), "c.db"))

    def tearDown(self):
        self.cache.close()

    def test_roundtrip(self):
        self.cache.put("u", {"a": 1})
        self.assertEqual(self.cache.get("u", 3600), {"a": 1})

    def test_miss_returns_none(self):
        self.assertIsNone(self.cache.get("nope", 3600))

    def test_expiry(self):
        self.cache.put("u", {"a": 1})
        self.assertIsNone(self.cache.get("u", -1))

    def test_forget(self):
        self.cache.put("u", {"a": 1})
        self.cache.forget("u")
        self.assertIsNone(self.cache.get("u", 3600))


class TestRender(unittest.TestCase):

    def test_writes_self_contained_html(self):
        population = [app(reviews=500, name="A"), app(reviews=50, name="B")]
        summary = analyze.summarise(population, population[:1], {"name": "Test"})
        path = os.path.join(tempfile.mkdtemp(), "index.html")
        render.render(population, population[:1], summary, {"name": "Test"}, path)
        with open(path, encoding="utf-8") as fh:
            doc = fh.read()
        self.assertIn("<!doctype html>", doc)
        self.assertNotIn("<script src", doc)
        self.assertIn("prefers-color-scheme", doc)
        # The estimate warning is not optional.
        self.assertIn("estimate", doc.lower())

    def test_escapes_game_names(self):
        population = [app(name='<img src=x onerror="alert(1)">')]
        summary = analyze.summarise(population, population, {"name": "T"})
        path = os.path.join(tempfile.mkdtemp(), "index.html")
        render.render(population, population, summary, {"name": "T"}, path)
        with open(path, encoding="utf-8") as fh:
            doc = fh.read()
        self.assertNotIn("<img src=x", doc)


class TestRandomSlice(unittest.TestCase):
    """The report shows the biggest games; contamination hides near the median.

    A "modern-military RTS" niche was found to contain Laptop Tycoon - it
    carries RTS and Modern, and Modern means modern *setting*. Nothing in the
    report would have shown that, because Laptop Tycoon is nowhere near the top.
    """

    def population(self, n=60):
        return [app(reviews=10 * i + 5, name="Game %d" % i) for i in range(n)]

    def test_returns_the_requested_number(self):
        self.assertEqual(len(analyze.random_slice(self.population(), 12)), 12)

    def test_is_deterministic_for_a_seed(self):
        pop = self.population()
        first = [a["name"] for a in analyze.random_slice(pop, 10, seed=3)]
        second = [a["name"] for a in analyze.random_slice(pop, 10, seed=3)]
        self.assertEqual(first, second)

    def test_different_seeds_differ(self):
        pop = self.population()
        a = [x["name"] for x in analyze.random_slice(pop, 10, seed=1)]
        b = [x["name"] for x in analyze.random_slice(pop, 10, seed=2)]
        self.assertNotEqual(a, b)

    def test_it_is_not_the_top_of_the_list(self):
        pop = self.population()
        top = {a["name"] for a in sorted(
            pop, key=lambda x: x["total_reviews"], reverse=True)[:12]}
        drawn = {a["name"] for a in analyze.random_slice(pop, 12, seed=0)}
        self.assertNotEqual(top, drawn)

    def test_small_population_is_not_oversampled(self):
        self.assertEqual(len(analyze.random_slice(self.population(3), 12)), 3)

    def test_empty_population_is_harmless(self):
        self.assertEqual(analyze.random_slice([], 12), [])

    def test_the_slice_reaches_the_summary(self):
        pop = self.population()
        summary = analyze.summarise(pop, pop[:5], {"name": "n"})
        self.assertEqual(len(summary["random_slice"]), 12)


class TestDateFilterScope(unittest.TestCase):
    """REGRESSION: released_since was declared in config and silently ignored.

    Release years only exist after the per-game pass, so the filter could never
    touch the population that produces the headline revenue figures. The key is
    now named for its scope and the report states it outright.
    """

    def test_the_new_key_filters_the_sample(self):
        ok, why = collect.keeps(app(year=2012), {"sample_released_since": 2016})
        self.assertFalse(ok)
        self.assertIn("2016", why)

    def test_the_old_key_still_works(self):
        ok, _ = collect.keeps(app(year=2012), {"released_since": 2016})
        self.assertFalse(ok)

    def test_population_records_carry_no_year_to_filter_on(self):
        record = collect.population_record("1", {"name": "X", "positive": 50,
                                                 "negative": 5})
        self.assertIsNone(record["release_year"])

    def test_the_scope_is_reported_so_it_cannot_mislead(self):
        pop = [app(name="P%d" % i) for i in range(20)]
        summary = analyze.summarise(pop, pop[:5], {"sample_released_since": 2016})
        self.assertEqual(summary["sample_released_since"], 2016)

    def test_the_report_states_the_scope(self):
        pop = [app(name="P%d" % i) for i in range(20)]
        niche = {"name": "T", "sample_released_since": 2016}
        summary = analyze.summarise(pop, pop[:5], niche)
        path = os.path.join(tempfile.mkdtemp(), "index.html")
        render.render(pop, pop[:5], summary, niche, path)
        with open(path, encoding="utf-8") as fh:
            doc = fh.read()
        self.assertIn("all release years", doc)


if __name__ == "__main__":
    unittest.main(verbosity=2)
