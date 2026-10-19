"""Which features go with the games in a niche that sold, and what players ask for.

Two questions, answered from different data and never mixed:

  compare - store-page features and tags, compared between the games that
            earned more and the ones that earned less. The sample is drawn
            AT RANDOM from the population, not the top of it. analyze's
            tag_performance runs on the biggest N, where every game sold, so
            it can say what winners carry but not what losers also carry. A
            feature on 90% of hits is uninformative if it is on 90% of flops
            too, and only a sample that holds the flops can show that.

  asks    - sentences from the most helpful reviews of the niche's biggest
            games where a player says what is missing: "I wish", "needs
            more", "if only". These are first-person voices with a link
            each, which is what Gate 1 counts and desk searches rarely find.

What neither can say:

  * Cause. A feature on the games that earned more may be riding on them. Some
    are earned BY selling: Valve grants Steam Trading Cards only after a game
    passes its confidence threshold, and studios make DLC for games that
    sold. Those are marked and should be read backwards.
  * Anything about games under the niche's min_reviews. The true flops,
    with a handful of reviews, are not in the population, so this compares
    modest games with big ones rather than failures with successes.
  * Era. Features come and go (Family Sharing was switched on for nearly
    every game in 2024). The median release year of each side is printed so
    a feature that mostly sits on older or newer games shows itself.
"""

import collections
import random
import re

from . import analyze, collect, revenue, sources

# Earned after success, so a higher median is the sales causing the feature.
EARNED = {
    "cat: Steam Trading Cards": "Valve grants cards only after a game sells",
    "has DLC": "studios make DLC for games that sold",
}

MIN_N = 8
BOOTS = 1000


def features_of(app):
    """The set of feature labels a store record carries."""
    out = set()
    for name in app.get("categories") or ():
        out.add("cat: %s" % name)
    # Controller support is not added from app["controller"]: Steam already
    # lists it as a category ("Full controller support", "Partial Controller
    # Support"), and adding it again printed the same comparison three times.
    for platform in app.get("platforms") or ():
        if platform != "windows":
            out.add("runs on %s" % platform)
    langs = app.get("languages") or 0
    if langs >= 5:
        out.add("5+ languages")
    if langs >= 10:
        out.add("10+ languages")
    if app.get("early_access"):
        out.add("Early Access on the store page")
    if (app.get("dlc_count") or 0) > 0:
        out.add("has DLC")
    for tag in app.get("tags") or {}:
        out.add("tag: %s" % tag)
    return out


def _ratio(with_values, without_values):
    a = analyze.percentile(with_values, 0.5)
    b = analyze.percentile(without_values, 0.5)
    if not a or not b:
        return None
    return a / float(b)


def compare(apps, min_n=MIN_N, boots=BOOTS, seed=0, skip=()):
    """One row per feature carried by at least min_n paid games and missing
    from at least min_n.

    ratio is the median revenue of games with the feature over the median of
    games without it, with a 90% bootstrap interval. top_share and
    bottom_share are how often the feature appears in the top quarter and the
    bottom half by revenue, which reads more plainly than a ratio.
    """
    paid = [a for a in apps if not a["estimate"].get("free")
            and (a["estimate"].get("revenue_mid") or 0) > 0]
    if len(paid) < 2 * min_n:
        return []
    ranked = sorted(paid, key=lambda a: a["estimate"]["revenue_mid"], reverse=True)
    top = ranked[:max(1, len(ranked) // 4)]
    bottom = ranked[len(ranked) // 2:]

    carried = [(a, features_of(a)) for a in paid]
    has = {id(a): f for a, f in carried}
    skip = {s.lower() for s in skip}
    labels = set().union(*(f for _, f in carried))
    picker = random.Random(seed)
    rows = []
    for label in sorted(labels):
        if label.lower() in skip:
            continue
        with_apps = [a for a, f in carried if label in f]
        without_apps = [a for a, f in carried if label not in f]
        if len(with_apps) < min_n or len(without_apps) < min_n:
            continue
        w = [a["estimate"]["revenue_mid"] for a in with_apps]
        wo = [a["estimate"]["revenue_mid"] for a in without_apps]
        ratio = _ratio(w, wo)
        if ratio is None:
            continue
        draws = []
        for _ in range(boots):
            r = _ratio([picker.choice(w) for _ in w], [picker.choice(wo) for _ in wo])
            if r is not None:
                draws.append(r)
        lo = analyze.percentile(draws, 0.05)
        hi = analyze.percentile(draws, 0.95)
        if lo is not None and lo > 1:
            reading = "higher"
        elif hi is not None and hi < 1:
            reading = "lower"
        else:
            reading = "no clear difference"
        rows.append({
            "feature": label,
            "n_with": len(w),
            "n_without": len(wo),
            "median_with": analyze.percentile(w, 0.5),
            "median_without": analyze.percentile(wo, 0.5),
            "ratio": ratio,
            "lo": lo,
            "hi": hi,
            "reading": reading,
            "top_share": sum(1 for a in top if label in has[id(a)]) / float(len(top)),
            "bottom_share": sum(1 for a in bottom if label in has[id(a)]) / float(len(bottom)),
            "year_with": analyze.percentile([a.get("release_year") for a in with_apps], 0.5),
            "year_without": analyze.percentile([a.get("release_year") for a in without_apps], 0.5),
            "earned": EARNED.get(label),
        })
    rows.sort(key=lambda r: r["ratio"], reverse=True)
    return rows


def random_sample(niche, cache, n=150, seed=0, log=None):
    """(kept, drawn, population, rejected): n games drawn at random from the
    niche's population and enriched, with the per-game filter applied."""
    pool = collect.candidates(niche, cache, log=log)
    min_reviews = niche.get("min_reviews") or 0
    population = []
    for appid, summary in pool.items():
        record = collect.population_record(appid, summary)
        if record["total_reviews"] >= min_reviews and collect.name_matches(record["name"], niche):
            population.append(record)
    population.sort(key=lambda r: r["appid"])   # a seed means the same draw
    drawn = analyze.random_slice(population, n, seed=seed)
    if log:
        log("  drawing %d at random from %d" % (len(drawn), len(population)))
    kept, rejected = [], collections.Counter()
    for i, record in enumerate(drawn, 1):
        appid = str(record["appid"])
        try:
            app = collect.enrich(appid, pool.get(appid) or {}, cache)
        except sources.SourceError:
            rejected["fetch failed"] += 1
            continue
        ok, why = collect.keeps(app, niche)
        if not ok:
            rejected[why] += 1
            continue
        app["estimate"] = revenue.estimate(app)
        kept.append(app)
        if log and i % 25 == 0:
            log("  ... %d/%d enriched, %d kept" % (i, len(drawn), len(kept)))
    return kept, len(drawn), population, rejected


# ---------------------------------------------------------------- asks

ASK = re.compile(
    r"\b(i wish|wish (it|there|they|you|the|i)|if only|would (be|have been) "
    r"(nice|great|cool|better|awesome)|i'?d love|would love|needs? (more|a|an|"
    r"better|some)|should (add|have|let|allow)|please add|lacks?|lacking|"
    r"missing|no way to)\b", re.I)
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")
_MARKUP = re.compile(r"\[/?[a-z0-9*]+[^\]]*\]", re.I)
_WORD = re.compile(r"[a-z][a-z'-]{3,}")
STOP = set("""
about after again also always another anything around back because been before
being better bought could didn't does doesn't doing done don't each even every
feel feels game games getting give going good gotta great have having here into
it's just keep know least less like little lot lots make makes many maybe more
most much need needs never nice only other really right same seem seems should
since some something still such sure take than that that's their them then there
these they thing things think this those though through time times very want
wants well were what when where which while will wish with without would wouldn't
yeah your you're lacks lacking missing love please hours play played playing
""".split())


def review_url(review, appid):
    steamid = (review.get("author") or {}).get("steamid")
    if not steamid:
        return None
    return "https://steamcommunity.com/profiles/%s/recommended/%d/" % (steamid, appid)


def extract_asks(reviews, appid, game):
    """Every sentence in these reviews that says what is missing, one row each."""
    out = []
    for review in reviews:
        text = _MARKUP.sub(" ", review.get("review") or "")
        for sentence in _SENTENCE.split(text):
            sentence = " ".join(sentence.split())
            if 12 <= len(sentence) and ASK.search(sentence):
                out.append({
                    "game": game,
                    "appid": appid,
                    "review_id": review.get("recommendationid"),
                    "text": sentence[:300],
                    "votes_up": review.get("votes_up") or 0,
                    "positive": bool(review.get("voted_up")),
                    "hours": round(((review.get("author") or {}).get("playtime_forever") or 0) / 60.0),
                    "created": review.get("timestamp_created"),
                    "url": review_url(review, appid),
                })
    return out


def themes(asks, top=25):
    """The words that recur across ask sentences, counted once per review."""
    reviews = collections.defaultdict(set)
    games = collections.defaultdict(set)
    for ask in asks:
        for word in set(_WORD.findall(ask["text"].lower())):
            if word in STOP:
                continue
            reviews[word].add((ask["appid"], ask["review_id"]))
            games[word].add(ask["appid"])
    rows = [{"word": w, "reviews": len(r), "games": len(games[w])}
            for w, r in reviews.items() if len(r) >= 2]
    rows.sort(key=lambda r: (-r["reviews"], -r["games"], r["word"]))
    return rows[:top]


def gather_asks(population, cache, games=8, log=None):
    """Asks from the most helpful reviews of the niche's most-reviewed games."""
    biggest = sorted(population, key=lambda r: r["total_reviews"], reverse=True)[:games]
    asks, read = [], []
    for record in biggest:
        try:
            reviews = sources.review_texts(int(record["appid"]), cache=cache)
        except sources.SourceError as exc:
            if log:
                log("  ! %s" % exc)
            continue
        found = extract_asks(reviews, int(record["appid"]), record.get("name"))
        read.append((record.get("name"), len(reviews), len(found)))
        asks.extend(found)
    return asks, read


# ---------------------------------------------------------------- report

def _money(value):
    if value is None:
        return "-"
    if value >= 1000000:
        return "$%.1fM" % (value / 1000000.0)
    if value >= 1000:
        return "$%dk" % round(value / 1000.0)
    return "$%d" % round(value)


def _row(r):
    mark = " (earned)" if r["earned"] else ""
    years = "%s/%s" % (r["year_with"] or "-", r["year_without"] or "-")
    return ("  %-38s %4d %4d  %7s %7s  %4.1fx (%.1f-%.1f)  %3.0f%% / %3.0f%%  %s"
            % ((r["feature"] + mark)[:38], r["n_with"], r["n_without"],
               _money(r["median_with"]), _money(r["median_without"]),
               r["ratio"], r["lo"] or 0, r["hi"] or 0,
               100 * r["top_share"], 100 * r["bottom_share"], years))


def report(niche, rows, kept, drawn, population, rejected, asks, read, quotes=30):
    out = []
    add = out.append
    paid = [a for a in kept if not a["estimate"].get("free")]
    add("FEATURES - %s" % niche.get("name"))
    add("=" * 72)
    add("Random sample: %d drawn from a population of %d (games with %d+ reviews);"
        % (drawn, len(population), niche.get("min_reviews") or 0))
    add("%d kept after the per-game filter, %d of them paid. Rejected: %s."
        % (len(kept), len(paid), ", ".join("%s %d" % kv for kv in sorted(rejected.items())) or "none"))
    since = niche.get("sample_released_since") or niche.get("released_since")
    if since:
        add("Released %s or later only (the niche's sample_released_since)." % since)
    add("")
    add("Revenue is Greenlight's estimate from reviews. A higher median WITH a")
    add("feature is association, not cause; '(earned)' marks features that sales")
    add("produce. Games under %d reviews are not in the population, so this"
        % (niche.get("min_reviews") or 0))
    add("compares modest games with big ones, not flops with hits.")
    add("")
    head = ("  %-38s %4s %4s  %7s %7s  %-16s %-13s %s"
            % ("feature", "with", "w/o", "med w", "med w/o", "ratio (90%)",
               "top25%/bot50%", "year w/w-o"))
    for title, reading in (("CLEARLY HIGHER WITH IT", "higher"),
                           ("CLEARLY LOWER WITH IT", "lower")):
        chosen = [r for r in rows if r["reading"] == reading]
        add("%s (%d)" % (title, len(chosen)))
        if chosen:
            add(head)
            for r in (chosen if reading == "higher" else chosen[::-1]):
                add(_row(r))
        else:
            add("  none: no feature's interval clears 1 at this sample size")
        add("")
    unclear = sorted((r for r in rows if r["reading"] == "no clear difference"),
                     key=lambda r: -min(r["n_with"], r["n_without"]))
    add("NO CLEAR DIFFERENCE, most evenly split first (%d)" % len(unclear))
    if unclear:
        add(head)
        for r in unclear[:15]:
            add(_row(r))
    add("")
    add("WHAT PLAYERS SAY IS MISSING")
    add("Sentences with 'I wish', 'needs more', 'if only' and the like, from the")
    add("most helpful English reviews (one page each) of the niche's most-reviewed")
    add("games. Positive reviews' asks are what fans want added; negative ones'")
    add("are why players left.")
    for game, n_reviews, n_asks in read:
        add("  %-44s %3d reviews read, %3d ask sentences" % ((game or "?")[:44], n_reviews, n_asks))
    add("")
    words = themes(asks)
    if words:
        add("  Recurring words (reviews / games):")
        add("  " + ", ".join("%s %d/%d" % (w["word"], w["reviews"], w["games"]) for w in words))
        add("")
    ranked = sorted(asks, key=lambda a: -a["votes_up"])
    for a in ranked[:quotes]:
        add("  [%s, %s, %dh, %d helpful] %s"
            % ((a["game"] or "?")[:28], "+" if a["positive"] else "-",
               a["hours"], a["votes_up"], a["text"]))
        if a["url"]:
            add("      %s" % a["url"])
    if not asks:
        add("  none found")
    return "\n".join(out) + "\n"
