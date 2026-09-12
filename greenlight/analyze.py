"""What the niche actually looks like, once the games are in hand.

The averages are useless here and deliberately absent. Steam revenue is a power
law: a handful of titles take almost everything and the median game earns a
rounding error next to them. An average across that distribution describes no
game that exists, and quoting one is how a genre looks viable right up until you
ship into it.

So everything below is percentiles, counts and shares.
"""

import collections
import random
import statistics


def percentile(values, p):
    """The p-th percentile (0..1) by nearest rank. Empty list gives None."""
    ordered = sorted(v for v in values if v is not None)
    if not ordered:
        return None
    if len(ordered) == 1:
        return ordered[0]
    index = min(len(ordered) - 1, max(0, int(round(p * (len(ordered) - 1)))))
    return ordered[index]


def revenue_distribution(apps):
    """Percentiles of estimated net revenue, plus how concentrated it is."""
    paid = [a for a in apps if not a["estimate"].get("free")]
    values = [a["estimate"].get("revenue_mid") or 0 for a in paid]
    if not values:
        return {"n": 0}

    total = sum(values)
    ordered = sorted(values, reverse=True)
    top_share = sum(ordered[:max(1, len(ordered) // 10)]) / total if total else 0

    return {
        "n": len(values),
        "p10": percentile(values, 0.10),
        "p25": percentile(values, 0.25),
        "median": percentile(values, 0.50),
        "p75": percentile(values, 0.75),
        "p90": percentile(values, 0.90),
        "max": max(values),
        "total": total,
        "top_decile_share": top_share,
        "under_10k": sum(1 for v in values if v < 10000),
        "under_50k": sum(1 for v in values if v < 50000),
        "over_1m": sum(1 for v in values if v >= 1000000),
    }


def price_points(apps):
    """What the niche charges, and what each price band earns."""
    bands = collections.defaultdict(list)
    for app in apps:
        est = app["estimate"]
        if est.get("free"):
            bands["free"].append(0)
            continue
        price = (app.get("price_cents") or 0) / 100.0
        if price < 10:
            label = "under $10"
        elif price < 20:
            label = "$10-19"
        elif price < 30:
            label = "$20-29"
        elif price < 45:
            label = "$30-44"
        else:
            label = "$45+"
        bands[label].append(est.get("revenue_mid") or 0)

    order = ["free", "under $10", "$10-19", "$20-29", "$30-44", "$45+"]
    return [{
        "band": label,
        "n": len(bands[label]),
        "median_revenue": percentile(bands[label], 0.5),
        "share": len(bands[label]) / float(len(apps)) if apps else 0,
    } for label in order if bands.get(label)]


def tag_performance(apps, min_apps=4, exclude=()):
    """Median revenue of games carrying each tag, against the niche median.

    A tag that appears on the games earning more is not proof it causes anything
    - popular tags ride on popular games. It is a signal about what the paying
    audience in this niche is actually looking for, and that is worth knowing
    before you pick five tags at launch and live with them.
    """
    paid = [a for a in apps if not a["estimate"].get("free")]
    if not paid:
        return []
    baseline = percentile([a["estimate"].get("revenue_mid") or 0 for a in paid], 0.5)
    if not baseline:
        return []

    skip = {t.lower() for t in exclude}
    buckets = collections.defaultdict(list)
    for app in paid:
        for tag in (app.get("tags") or {}):
            if tag.lower() in skip:
                continue
            buckets[tag].append(app["estimate"].get("revenue_mid") or 0)

    rows = []
    for tag, values in buckets.items():
        if len(values) < min_apps:
            continue
        median = percentile(values, 0.5)
        rows.append({
            "tag": tag,
            "n": len(values),
            "median_revenue": median,
            "vs_niche": (median / baseline) if baseline else None,
        })
    rows.sort(key=lambda r: r["vs_niche"] or 0, reverse=True)
    return rows


def release_cadence(apps):
    """How many games ship into this niche each year, and how they do."""
    years = collections.defaultdict(list)
    for app in apps:
        year = app.get("release_year")
        if year:
            years[year].append(app["estimate"].get("revenue_mid") or 0)
    return [{
        "year": year,
        "n": len(values),
        "median_revenue": percentile(values, 0.5),
    } for year, values in sorted(years.items())]


def review_thresholds(apps):
    """Review counts at each revenue percentile - the number to aim at.

    Reviews are the only public proxy for how a launch went, so knowing what
    review count corresponds to a survivable outcome gives a concrete target.
    """
    paid = [a for a in apps if not a["estimate"].get("free")
            and (a.get("total_reviews") or 0) > 0]
    if not paid:
        return {}
    paid.sort(key=lambda a: a["estimate"].get("revenue_mid") or 0)
    out = {}
    for label, p in (("median", 0.5), ("top quarter", 0.75), ("top tenth", 0.9)):
        index = min(len(paid) - 1, int(p * (len(paid) - 1)))
        app = paid[index]
        out[label] = {
            "reviews": app.get("total_reviews"),
            "revenue": app["estimate"].get("revenue_mid"),
            "name": app.get("name"),
        }
    return out


def reception(apps):
    """Does the niche review well? A hostile audience is worth knowing about."""
    rates = []
    for app in apps:
        total = app.get("total_reviews") or 0
        if total >= 30:
            rates.append(app.get("positive", 0) / float(total))
    if not rates:
        return {}
    return {
        "n": len(rates),
        "median_positive": statistics.median(rates),
        "share_above_80": sum(1 for r in rates if r >= 0.8) / float(len(rates)),
    }


def random_slice(population, n=12, seed=0):
    """A random handful of the population, for eyeballing what is actually in it.

    The report otherwise shows only the biggest games, which is exactly where
    contamination hides. A "modern-military RTS" niche turned out to contain
    Laptop Tycoon - it carries RTS and Modern - and that only surfaced by
    accident while looking at something else. Ten random rows would have made it
    obvious on the first run.

    Seeded, so re-running the same niche shows the same games and a change in
    this list means the niche changed rather than the dice.
    """
    if not population:
        return []
    picker = random.Random(seed)
    return picker.sample(population, min(n, len(population)))


def summarise(population, sample, niche):
    """Each question answered from the dataset that can honestly answer it.

    The revenue distribution, prices and reception come from the whole
    population, because those are the questions where a biased sample gives a
    flattering lie. Tags and release cadence come from the enriched sample,
    because they need per-game detail that costs a request each - and both are
    labelled as "the biggest N" wherever they are shown.
    """
    return {
        "niche": niche.get("name"),
        "population": len(population),
        "sample": len(sample),
        "revenue": revenue_distribution(population),
        "prices": price_points(population),
        "thresholds": review_thresholds(population),
        "reception": reception(population),
        "tags": tag_performance(sample, exclude=niche.get("require_tags") or ()),
        "cadence": release_cadence(sample),
        "confidence": collections.Counter(a.get("confidence") for a in population),
        "random_slice": random_slice(population),
        # The population has no release years - they only arrive with the
        # expensive per-game pass - so any date filter applies to the sample
        # alone. Stated here so the report cannot imply otherwise.
        "sample_released_since": niche.get("sample_released_since")
        or niche.get("released_since"),
    }
