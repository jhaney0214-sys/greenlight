"""The copies estimate against games whose real sales are known.

    python tools/validate.py            # fetch the survey once, then report
    python tools/validate.py --offline  # from the cached copy only

Greenlight turns a review count into copies with a multiplier chosen by
release year (`greenlight/revenue.py`). Until 2026-10-13 that had never been
compared with a game whose sales were known. GameDiscoverCo's October 2022
survey is the comparison: about 200 Steam games, each with the review count
on its store page and the lifetime units from the developer's own Steam back
end, published as a spreadsheet with its article of 2022-11-14
(newsletter.gamediscover.co/p/steam-sales-estimates-why-game-popularity).

The rows are GameDiscoverCo's and are not copied into this repository. They
are fetched into `data/cache/`, which git ignores; what is kept is the report.

What this checks is reviews to copies. It says nothing about copies to
dollars: the survey has no prices and no revenue.
"""

import argparse
import csv
import io
import os
import statistics
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from greenlight import revenue  # noqa: E402

SHEET = ("https://docs.google.com/spreadsheets/d/"
         "1lTLN1aSYNDfgg8winAcPShKCNGn0yy1y/export?format=csv")
CACHE = os.path.join(ROOT, "data", "cache", "gamediscoverco-2022-10.csv")
#: The survey's oldest answer is "Before 2016".
BEFORE = 2015


def parse(text):
    """[(year, flags, reviews, units)] for every paid game with both numbers.

    Free-to-play rows are left out: their units are installs, not sales."""
    games = []
    for row in csv.reader(io.StringIO(text)):
        if len(row) < 4:
            continue
        year, flags, reviews, units = (cell.strip() for cell in row[:4])
        try:
            reviews = int(float(reviews.replace(",", "")))
            units = int(float(units.replace(",", "")))
        except ValueError:
            continue                      # the title and header rows
        if reviews <= 0 or units <= 0 or "Free" in flags:
            continue
        if year.startswith("Before"):
            year = BEFORE
        elif year.isdigit():
            year = int(year)
        else:
            continue
        games.append((year, flags, reviews, units))
    return games


def errors(games):
    """Estimated copies over real copies, one per game. 1.0 is exact."""
    return [reviews * revenue.review_multiplier(year) / units
            for year, _, reviews, units in games]


def quartiles(values):
    ordered = sorted(values)
    return (ordered[len(ordered) // 4], statistics.median(ordered),
            ordered[(3 * len(ordered)) // 4])


def summary(games):
    """What the estimate did over one group of games, or None if it is empty."""
    if not games:
        return None
    ratio = errors(games)
    low, high = 1 - revenue.MULTIPLIER_SPREAD, 1 + revenue.MULTIPLIER_SPREAD
    # The real figure is inside the report's own range when
    # estimate * low <= real <= estimate * high.
    inside = sum(1 for r in ratio if 1 / high <= r <= 1 / low)
    within2 = sum(1 for r in ratio if 0.5 <= r <= 2.0)
    return {"n": len(games),
            "real_multiplier": quartiles([u / r for _, _, r, u in games]),
            "estimate_over_real": quartiles(ratio),
            "inside_range": inside / len(games),
            "within_2x": within2 / len(games)}


def interval(games, share=0.8):
    """(low, high): the factors on the estimate that held the real copies for
    `share` of these games, split evenly at each end. The report's own range
    is 1 - MULTIPLIER_SPREAD to 1 + MULTIPLIER_SPREAD, and held 48% of the
    survey (2026-10-13); this is the range the survey says would hold `share`."""
    real_over_estimate = sorted(1 / r for r in errors(games))
    if len(real_over_estimate) < 10:
        return None
    tail = (1 - share) / 2
    cut = statistics.quantiles(real_over_estimate, n=1000, method="inclusive")
    return cut[round(tail * 1000) - 1], cut[round((1 - tail) * 1000) - 1]


def groups(games):
    yield "every paid game", games
    for low, high in ((0, 30), (30, 100), (100, 1000), (1000, 10000), (10000, None)):
        label = ("%d reviews and over" % low if high is None
                 else "%d to %d reviews" % (low, high - 1))
        yield label, [g for g in games if g[2] >= low and (high is None or g[2] < high)]
    for low, high, label in ((BEFORE, BEFORE, "released before 2016"),
                             (2016, 2019, "released 2016-2019"),
                             (2020, 2021, "released 2020-2021"),
                             (2022, 2022, "released 2022")):
        yield label, [g for g in games if low <= g[0] <= high]
    yield "in Early Access", [g for g in games if "Early" in g[1]]
    yield ("released 2020-2022, under 1,000 reviews",
           [g for g in games if g[0] >= 2020 and g[2] < 1000])


def report(games):
    lines = ["%-40s %4s  %-17s  %-17s  %6s  %6s"
             % ("", "n", "real copies/review", "estimate / real", "in the", "within"),
             "%-40s %4s  %-17s  %-17s  %6s  %6s"
             % ("", "", "q1   median   q3", "q1   median   q3", "range", "2x")]
    for label, group in groups(games):
        s = summary(group)
        if s is None:
            continue
        lines.append("%-40s %4d  %5.1f %5.1f %5.1f  %5.2f %5.2f %5.2f  %5.0f%%  %5.0f%%"
                     % ((label, s["n"]) + s["real_multiplier"] + s["estimate_over_real"]
                        + (100 * s["inside_range"], 100 * s["within_2x"])))
    return "\n".join(lines)


def fetch(offline=False):
    if not os.path.isfile(CACHE):
        if offline:
            sys.exit("no cached survey at %s; run once without --offline" % CACHE)
        request = urllib.request.Request(SHEET, headers={"User-Agent": "greenlight validate"})
        with urllib.request.urlopen(request, timeout=60) as response:
            raw = response.read()
        os.makedirs(os.path.dirname(CACHE), exist_ok=True)
        with open(CACHE + ".tmp", "wb") as handle:
            handle.write(raw)
        os.replace(CACHE + ".tmp", CACHE)
    with open(CACHE, encoding="utf-8") as handle:
        return handle.read()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--share", type=float, default=0.8,
                        help="the share of games the printed range should hold (default 0.8)")
    args = parser.parse_args(argv)
    games = parse(fetch(args.offline))
    print("GameDiscoverCo survey, October 2022: %d paid games with reviews and units"
          % len(games))
    print("range = the report's own low-to-high, the estimate -%d%% to +%d%%"
          % (100 * revenue.MULTIPLIER_SPREAD, 100 * revenue.MULTIPLIER_SPREAD))
    print()
    print(report(games))
    print()
    print("The range that would have held %d%% of these games, as factors on the estimate"
          % (100 * args.share))
    print("(the report uses %.2f to %.2f):"
          % (1 - revenue.MULTIPLIER_SPREAD, 1 + revenue.MULTIPLIER_SPREAD))
    for label, group in groups(games):
        found = interval(group, args.share)
        if found:
            print("  %-40s %4d  %5.2f to %5.2f" % (label, len(group), found[0], found[1]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
