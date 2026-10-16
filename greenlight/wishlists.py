"""Wishlists at launch to units sold, from pairs developers published.

Before launch a developer holds wishlists, not reviews, so the review-based
model in revenue.py cannot answer "what will my game sell". This module
answers it the only way public data allows: from games whose developers or
publishers printed both numbers, collected with a link and a date each in
data/wishlist_pairs.json.

What is measured and what is not:

* Each pair is a published figure. Nothing in the data file is estimated here.
* The range for *your* game is an estimate. It assumes your game is drawn from
  the same population as these pairs, and it is not: most were published
  because the game sold well. The report says so and shows how much it matters
  by splitting the success stories from the rest.
* The error stated is measured: each pair is held out in turn, the range is
  refitted on the others, and the report counts how often the held-out game's
  real ratio fell inside.
* The first-year figure is not fitted from pairs (almost nobody publishes one).
  It is the first-week range times GameDiscoverCo's median year-one multiplier,
  which is itself their estimate, and it is labelled as such.
"""

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "data", "wishlist_pairs.json")

#: (label, shortest, longest, nominal) days after launch.
WINDOWS = (
    ("first day", 0, 3, 1),
    ("first week", 4, 14, 7),
    ("first month", 15, 60, 30),
    ("first year", 300, 450, 365),
)

#: Below this many games a window gets its pairs listed, not a fitted range.
MIN_FIT = 8

QUANTILES = (0.10, 0.25, 0.50, 0.75, 0.90)

#: Selections that were not picked for selling well.
NOT_PICKED_FOR_SUCCESS = ("own devlog", "underperformer story", "survey example")

PRICE_SPLIT = 10.0


def load(path=DATA):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def usable(pairs):
    """Rows that can be fitted: unflagged, with a stated window and both counts."""
    return [p for p in pairs
            if not p.get("flags") and p.get("days") is not None
            and (p.get("wishlists") or 0) > 0 and (p.get("units") or 0) > 0]


def in_window(pairs, window):
    """One row per game in this window, the one nearest the window's nominal day."""
    _, low, high, nominal = window
    best = {}
    for p in usable(pairs):
        if low <= p["days"] <= high:
            current = best.get(p["game"])
            if current is None or abs(p["days"] - nominal) < abs(current["days"] - nominal):
                best[p["game"]] = p
    return sorted(best.values(), key=lambda p: p["units"] / p["wishlists"])


def ratio(p):
    return p["units"] / p["wishlists"]


def quantile(values, q):
    """Linear interpolation between order statistics (R's type 7)."""
    ordered = sorted(values)
    if not ordered:
        raise ValueError("no values")
    position = q * (len(ordered) - 1)
    below = int(position)
    above = min(below + 1, len(ordered) - 1)
    return ordered[below] + (ordered[above] - ordered[below]) * (position - below)


def fit(values):
    return {q: quantile(values, q) for q in QUANTILES}


def held_out(values, low_q, high_q):
    """Share of games whose real ratio fell inside the range fitted without them."""
    if len(values) < 3:
        return None
    inside = 0
    for i, value in enumerate(values):
        rest = values[:i] + values[i + 1:]
        if quantile(rest, low_q) <= value <= quantile(rest, high_q):
            inside += 1
    return inside / len(values)


def held_out_within(values, factor=2.0):
    """Share of games within `factor` of the median fitted without them."""
    if len(values) < 3:
        return None
    hits = 0
    for i, value in enumerate(values):
        median = quantile(values[:i] + values[i + 1:], 0.5)
        if median / factor <= value <= median * factor:
            hits += 1
    return hits / len(values)


def price_band(price):
    return "under $%d" % PRICE_SPLIT if price < PRICE_SPLIT else "$%d and over" % PRICE_SPLIT


def summarise(rows):
    values = [ratio(p) for p in rows]
    picked = [ratio(p) for p in rows if p["selection"] not in NOT_PICKED_FOR_SUCCESS]
    others = [ratio(p) for p in rows if p["selection"] in NOT_PICKED_FOR_SUCCESS]
    return {
        "n": len(values),
        "fit": fit(values) if len(values) >= MIN_FIT else None,
        "middle_half_held": held_out(values, 0.25, 0.75),
        "q10_q90_held": held_out(values, 0.10, 0.90),
        "within_2x": held_out_within(values),
        "success_n": len(picked),
        "success_median": quantile(picked, 0.5) if picked else None,
        "other_n": len(others),
        "other_median": quantile(others, 0.5) if others else None,
        "years": sorted({str(p.get("launch", ""))[:4] for p in rows if p.get("launch")}),
    }


def _units(wishlists, r):
    units = wishlists * r
    if units >= 100:
        return format(int(round(units, -1 if units < 1000 else -2)), ",")
    return format(int(round(units)), ",")


def report(wishlists, price=None, data=None):
    data = data or load()
    pairs = data["pairs"]
    out = []
    out.append("WISHLISTS TO SALES - %s wishlists at launch%s"
               % (format(wishlists, ","),
                  "" if price is None else ", $%.2f" % price))
    out.append("=" * 72)
    out.append("Measured: every pair is a number a developer or publisher published")
    out.append("(data/wishlist_pairs.json, %d rows, %d games, each with a link and"
               % (len(pairs), len({p["game"] for p in pairs})))
    out.append("a date). Estimated: the range for your game, which assumes your game")
    out.append("is like these. Most of them are not like a typical launch; see below.")
    flagged = [p for p in pairs if p.get("flags")]
    undated = [p for p in pairs if not p.get("flags") and p.get("days") is None]
    out.append("Left out of every fit: %d flagged rows (a broken launch, a players"
               % len(flagged))
    out.append("count, an ambiguous percentage) and %d with no stated period."
               % len(undated))

    week = None
    for window in WINDOWS:
        rows = in_window(pairs, window)
        label, low, high, _ = window
        s = summarise(rows)
        out.append("")
        out.append("%s (%s to %s days after launch): n = %d %s, launched %s"
                   % (label.upper(), low, high, s["n"], "game" if s["n"] == 1 else "games",
                      "-".join(sorted({s["years"][0], s["years"][-1]})) if s["years"] else "?"))
        if s["fit"] is None:
            out.append("  Too few pairs to fit a range (fewer than %d). The pairs:" % MIN_FIT)
            for p in rows:
                out.append("    %-34s %9s wishlists %9s units  %.2f per wishlist"
                           % (p["game"][:34], format(p["wishlists"], ","),
                              format(p["units"], ","), ratio(p)))
            continue
        f = s["fit"]
        out.append("  units per wishlist   10%%: %.2f   25%%: %.2f   median: %.2f   75%%: %.2f   90%%: %.2f"
                   % tuple(f[q] for q in QUANTILES))
        out.append("  your units           10%%: %s   25%%: %s   median: %s   75%%: %s   90%%: %s"
                   % tuple(_units(wishlists, f[q]) for q in QUANTILES))
        out.append("  measured error (each game held out, range refitted on the rest):")
        out.append("    the middle half (25%%-75%%) held the real figure for %.0f%% of games"
                   % (100 * s["middle_half_held"]))
        out.append("    the 10%%-90%% range held it for %.0f%%; %.0f%% were within 2x of the median"
                   % (100 * s["q10_q90_held"], 100 * s["within_2x"]))
        if s["success_n"] and s["other_n"]:
            out.append("  selection: %d of %d were written up because they sold well (median %.2f);"
                       % (s["success_n"], s["n"], s["success_median"]))
            out.append("    the other %d (own devlogs, flops, survey rows): median %.2f."
                       % (s["other_n"], s["other_median"]))
        if label == "first week":
            week = (rows, f)

    out.append("")
    out.append("SURVEYS THAT ASKED EVERYONE, NOT JUST THE HITS (first week, medians only)")
    for b in data.get("benchmarks", []):
        out.append("  %.2f  %s; %s; n %s (%s)"
                   % (b["value"], b["what"], b["years"], b["n"], b["source_date"]))
    out.append("  These sit far below the published pairs' median. The pairs overstate a")
    out.append("  typical launch; treat the survey medians as the centre and the pairs'")
    out.append("  spread as how wide the outcomes run.")

    if price is not None:
        band = price_band(price)
        out.append("")
        out.append("PRICE (%s)" % band)
        rows = [p for p in (week[0] if week else [])
                if p.get("price_usd") is not None and price_band(p["price_usd"]) == band]
        if len(rows) < MIN_FIT:
            out.append("  Only %d first-week pairs state a price in this band; too few to fit."
                       % len(rows))
            for p in rows:
                out.append("    %-34s $%5.2f  %.2f per wishlist" % (p["game"][:34], p["price_usd"], ratio(p)))
        else:
            f = fit([ratio(p) for p in rows])
            out.append("  n = %d, median %.2f units per wishlist" % (len(rows), f[0.5]))
        if price >= PRICE_SPLIT:
            out.append("  GameDiscoverCo found games over $10 converted at about two thirds of the")
            out.append("  rate of all games (0.10 against 0.15 in 2024-25).")

    multiplier = data.get("year_one_multiplier")
    if week and multiplier:
        m = multiplier["value"]
        if price is not None:
            m = multiplier["under_10_usd"] if price < PRICE_SPLIT else multiplier["from_10_usd"]
        f = week[1]
        out.append("")
        out.append("FIRST YEAR - ESTIMATED, NOT MEASURED")
        out.append("  first-week units x %.2f, GameDiscoverCo's median year-one to week-one" % m)
        out.append("  multiplier (their own estimates, %s, published %s)."
                   % (multiplier["years"], multiplier["source_date"]))
        out.append("  25%%: %s   median: %s   75%%: %s units"
                   % tuple(_units(wishlists, f[q] * m) for q in (0.25, 0.5, 0.75)))
        surveys = [b["value"] for b in data.get("benchmarks", [])]
        if surveys:
            low, high = min(surveys), max(surveys)
            out.append("  from the survey medians instead (%.2f to %.2f a wishlist): %s to %s units"
                       % (low, high, _units(wishlists, low * m), _units(wishlists, high * m)))
        out.append("  The multiplier's own spread is not published, so these ranges are too narrow.")
    return "\n".join(out)
