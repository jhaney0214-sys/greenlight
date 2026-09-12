"""Assembling a niche: which games count, and what we know about each.

Enumeration is cheap - one SteamSpy call gets every app carrying a tag. Detail is
expensive: two more calls per app at a second and a half each. So the shape of
this module is "cast wide, rank, then only pay for the top of the list", and the
cap is a config knob rather than something buried here.
"""

import re
from datetime import datetime

from . import revenue, sources

_YEAR = re.compile(r"(19|20)\d{2}")


def release_year(raw):
    """Pull a year out of Steam's free-text release date, or None.

    Steam writes "Oct 28, 2021", "2021", "Q4 2024" and "Coming soon" in the same
    field, so this takes the first four-digit year it finds and refuses anything
    outside the range a Steam release could plausibly sit in.
    """
    if not raw:
        return None
    match = _YEAR.search(str(raw))
    if not match:
        return None
    year = int(match.group(0))
    return year if 1997 <= year <= datetime.now().year + 2 else None


def candidates(niche, cache, log=None):
    """Every app matching the niche's tag logic, with SteamSpy's summary.

    All of this is tag queries, which are one cheap cached call each, so the
    filtering happens across the *whole* population rather than a sample. That
    matters more than it sounds: ranking by review count and keeping the top
    slice makes the median game in the niche come out as Age of Empires II, and
    a survivorship-biased median is worse than no median at all.
    """
    required = niche.get("require_tags") or []
    if not required:
        raise ValueError("niche needs at least one entry in require_tags")

    base, pool = None, None
    for name in required:
        found = sources.tag(name, cache=cache)
        if log:
            log("  require %-20s %6d apps" % (name, len(found)))
        if base is None:
            base = dict(found)     # the first tag supplies the summary fields
        else:
            base.update(found)
        keys = set(found)
        pool = keys if pool is None else (pool & keys)

    any_tags = niche.get("any_tags") or []
    if any_tags:
        union = set()
        for name in any_tags:
            found = sources.tag(name, cache=cache)
            if log:
                log("  any     %-20s %6d apps" % (name, len(found)))
            base.update(found)
            union |= set(found)
        pool &= union
        if log:
            log("  after theme filter          %6d apps" % len(pool))

    for name in (niche.get("exclude_tags") or []):
        try:
            found = sources.tag(name, cache=cache)
        except sources.UnknownTag:
            if log:
                log("  ! exclude tag %r does not exist, skipped" % name)
            continue
        before = len(pool)
        pool -= set(found)
        if log and before != len(pool):
            log("  exclude %-20s %6d removed" % (name, before - len(pool)))

    return {appid: base[appid] for appid in (pool or ()) if appid in base}


def population_record(appid, summary):
    """A cheap record built only from SteamSpy's tag payload.

    No extra requests, so this covers the entire niche. It lacks a release year,
    which is why the revenue estimate here uses a single modern multiplier and
    says so, rather than pretending to per-game precision.
    """
    reviews = (summary.get("positive") or 0) + (summary.get("negative") or 0)
    price = summary.get("initialprice")
    price = int(price) if price not in (None, "") else 0
    return {
        "appid": int(appid),
        "name": summary.get("name"),
        "developer": summary.get("developer"),
        "total_reviews": reviews,
        "positive": summary.get("positive") or 0,
        "negative": summary.get("negative") or 0,
        "price_cents": price,
        "is_free": price == 0,
        "owners": summary.get("owners"),
        "release_year": None,
        "tags": {},
    }


def enrich(appid, summary, cache):
    """One app record, assembled from all three endpoints."""
    details = sources.app_details(int(appid), cache=cache)
    if not details:
        return None
    # DLC, soundtracks and demos carry their parent's tags and would otherwise
    # be counted as competing games.
    if details.get("type") != "game":
        return None

    reviews = sources.app_reviews(int(appid), cache=cache)
    spy = sources.app_tags(int(appid), cache=cache)

    price_info = details.get("price_overview") or {}
    price_cents = price_info.get("initial")
    if price_cents is None:
        price_cents = 0 if details.get("is_free") else (summary.get("initialprice") or 0)
        price_cents = int(price_cents or 0)

    tags = spy.get("tags") or {}
    if not isinstance(tags, dict):
        tags = {}

    return {
        "appid": int(appid),
        "name": details.get("name") or summary.get("name"),
        "developer": (details.get("developers") or [summary.get("developer")])[0]
        if (details.get("developers") or summary.get("developer")) else None,
        "publisher": (details.get("publishers") or [None])[0],
        "release_date": (details.get("release_date") or {}).get("date"),
        "release_year": release_year((details.get("release_date") or {}).get("date")),
        "coming_soon": bool((details.get("release_date") or {}).get("coming_soon")),
        "price_cents": int(price_cents or 0),
        "is_free": bool(details.get("is_free")) or int(price_cents or 0) == 0,
        "genres": [g.get("description") for g in (details.get("genres") or [])],
        "tags": tags,
        "total_reviews": int(reviews.get("total_reviews") or 0),
        "positive": int(reviews.get("total_positive") or 0),
        "negative": int(reviews.get("total_negative") or 0),
        "review_desc": reviews.get("review_score_desc"),
        "owners": summary.get("owners"),
        "ccu": summary.get("ccu"),
    }


def keeps(app, niche):
    """Whether an enriched record belongs in the analysis."""
    if app is None:
        return False, "not a game"
    if app.get("coming_soon"):
        return False, "unreleased"
    year = app.get("release_year")
    # Named for its scope: this only ever filters the enriched sample, because
    # the population has no release years to filter on. The old key still works.
    since = niche.get("sample_released_since") or niche.get("released_since")
    if since and (not year or year < since):
        return False, "older than %s" % since
    if app["total_reviews"] < (niche.get("min_reviews") or 0):
        return False, "under %d reviews" % niche.get("min_reviews", 0)

    tags = {t.lower() for t in (app.get("tags") or {})}
    exclude = {t.lower() for t in (niche.get("exclude_tags") or [])}
    if tags & exclude:
        return False, "excluded tag"

    any_tags = {t.lower() for t in (niche.get("any_tags") or [])}
    if any_tags and not (tags & any_tags):
        return False, "no matching theme tag"

    keywords = [k.lower() for k in (niche.get("keywords") or [])]
    if keywords:
        haystack = (app.get("name") or "").lower() + " " + " ".join(tags)
        if not any(k in haystack for k in keywords):
            return False, "no keyword match"
    return True, None


def build(niche, cache, log=None):
    """(population, sample, rejected).

    Two passes with different jobs, and they must not be confused for each other:

      population - every game matching the tag logic, priced from SteamSpy's own
                   fields. Free, unbiased, and the only honest source for "what
                   does a game in this niche earn".
      sample     - the biggest N, enriched with release dates and tag votes.
                   Necessarily survivorship-biased, so it is only used for the
                   questions where that does not matter: which tags appear on
                   games that sell, how the niche prices, when things shipped.
    """
    pool = candidates(niche, cache, log=log)
    min_reviews = niche.get("min_reviews") or 0

    population = []
    for appid, summary in pool.items():
        record = population_record(appid, summary)
        if record["total_reviews"] >= min_reviews:
            record["estimate"] = revenue.estimate(record)
            record["confidence"] = revenue.confidence(record, record["estimate"])
            population.append(record)
    population.sort(key=lambda a: a["estimate"].get("revenue_mid") or 0, reverse=True)
    if log:
        log("  population: %d games with >=%d reviews" % (len(population), min_reviews))

    # Rank by review count for the detail pass, and be explicit that this slice
    # is the top of the niche rather than a picture of it.
    def weight(item):
        summary = item[1] or {}
        return (summary.get("positive") or 0) + (summary.get("negative") or 0)

    ordered = sorted(pool.items(), key=weight, reverse=True)
    cap = niche.get("sample_cap") or 150
    ordered = ordered[:cap]
    if log:
        log("  enriching the top %d for tags and release dates" % len(ordered))

    apps, rejected = [], {}
    for index, (appid, summary) in enumerate(ordered, 1):
        try:
            record = enrich(appid, summary, cache)
        except sources.SourceError as exc:
            rejected["fetch failed"] = rejected.get("fetch failed", 0) + 1
            if log:
                log("  ! %s" % exc)
            continue
        ok, why = keeps(record, niche)
        if not ok:
            rejected[why] = rejected.get(why, 0) + 1
            continue
        record["estimate"] = revenue.estimate(record)
        record["confidence"] = revenue.confidence(record, record["estimate"])
        apps.append(record)
        if log and index % 25 == 0:
            log("  ... %d/%d checked, %d kept" % (index, len(ordered), len(apps)))

    apps.sort(key=lambda a: a["estimate"].get("revenue_mid") or 0, reverse=True)
    return population, apps, rejected
