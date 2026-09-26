"""Recent releases in a Greenlight niche, including the ones with almost no reviews.

The standard report's population is every app with >= min_reviews, across every
release year. For a launch decision the comparison set is recent releases, and
the games that got under ten reviews are part of the outcome, not noise.

    python tools/recent.py drone-rts 2021   (from the repository root)
"""
import collections
import json
import os
import sys

GL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, GL)
sys.path.insert(0, os.path.join(GL, "greenlight"))
from greenlight import collect, revenue, store, analyze   # noqa: E402

key = sys.argv[1] if len(sys.argv) > 1 else "drone-rts"
since = int(sys.argv[2]) if len(sys.argv) > 2 else 2021
niche = json.load(open(os.path.join(GL, "config", "niche.json")))["niches"][key]
cache = store.Cache()
pool = collect.candidates(niche, cache)
print("candidates (all review counts): %d" % len(pool), flush=True)

apps, why = [], collections.Counter()
for i, (appid, summary) in enumerate(sorted(pool.items())):
    try:
        app = collect.enrich(appid, summary, cache)
    except Exception as exc:                                  # noqa: BLE001
        why["fetch failed"] += 1
        continue
    if i % 50 == 0:
        print("  %d/%d" % (i, len(pool)), flush=True)
    if app is None:
        why["not a game"] += 1
        continue
    if app["coming_soon"]:
        why["unreleased"] += 1
        continue
    if not app["release_year"] or app["release_year"] < since:
        why["older"] += 1
        continue
    apps.append(app)

print("kept %d released %d or later; dropped %s" % (len(apps), since, dict(why)))
out = []
for a in apps:
    est = revenue.estimate(a)
    out.append(dict(a, est=est))
json.dump(out, open(os.path.join(GL, "out", "recent-%s-%d.json" % (key, since)), "w"))

def pct(vals, p):
    return analyze.percentile(vals, p / 100.0)

reviews = [a["total_reviews"] for a in out]
print("\nREVIEWS, every recent release (%d)" % len(reviews))
for p in (10, 25, 50, 75, 90):
    print("  p%-3d %8.0f" % (p, pct(reviews, p)))
for t in (0, 10, 50, 100, 500, 1000):
    print("  under %-5d %4d  %3.0f%%" % (t, sum(r < t for r in reviews), 100.0 * sum(r < t for r in reviews) / len(reviews)) if t else "  zero reviews %4d" % sum(r == 0 for r in reviews))

paid = [a for a in out if not a["is_free"]]
rev = [a["est"].get("revenue_mid", 0) if a["est"].get("known") else 0 for a in paid]
print("\nEST. LIFETIME NET REVENUE, paid recent releases (%d), no-review games counted as $0" % len(paid))
for p in (10, 25, 50, 75, 90):
    print("  p%-3d $%12s" % (p, format(round(pct(rev, p)), ",")))
for t in (1000, 10000, 50000, 100000, 1000000):
    n = sum(r >= t for r in rev)
    print("  >= $%-9s %4d  %4.1f%%" % (format(t, ","), n, 100.0 * n / len(rev)))

print("\nBY RELEASE YEAR: count, median reviews, median est. revenue (paid)")
for y in sorted({a["release_year"] for a in out}):
    ys = [a for a in out if a["release_year"] == y]
    yr = [a["est"].get("revenue_mid", 0) if a["est"].get("known") else 0 for a in ys if not a["is_free"]]
    print("  %d  %4d  %6.0f  $%s" % (y, len(ys), pct([a["total_reviews"] for a in ys], 50), format(round(pct(yr, 50)) if yr else 0, ",")))

print("\nBY PRICE (paid): count, median est. revenue, share >= $50k")
bands = [(0, 1000, "under $10"), (1000, 2000, "$10-19"), (2000, 3000, "$20-29"), (3000, 10**9, "$30+")]
for lo, hi, label in bands:
    g = [r for a, r in zip(paid, rev) if lo <= a["price_cents"] < hi]
    if g:
        print("  %-10s %4d  $%10s  %3.0f%%" % (label, len(g), format(round(pct(g, 50)), ","), 100.0 * sum(x >= 50000 for x in g) / len(g)))

selfpub = [(a, r) for a, r in zip(paid, rev) if a.get("publisher") and a.get("developer") and a["publisher"] == a["developer"]]
if selfpub:
    g = [r for _, r in selfpub]
    print("\nSELF-PUBLISHED paid (developer == publisher): %d, median $%s, >= $50k %.0f%%"
          % (len(g), format(round(pct(g, 50)), ","), 100.0 * sum(x >= 50000 for x in g) / len(g)))

print("\nRANDOM TWELVE (seeded):")
import random
rng = random.Random(0)
for a in rng.sample(out, min(12, len(out))):
    print("  %d  %-45s %6d reviews  $%.2f" % (a["release_year"], (a["name"] or "")[:45], a["total_reviews"], a["price_cents"] / 100.0))
