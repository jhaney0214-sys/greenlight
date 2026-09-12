#!/usr/bin/env python
"""Greenlight - is there a market for the game you are about to build?

    python gl.py niche drone-rts        analyse a niche from config/niche.json
    python gl.py niche drone-rts --open  and open the report
    python gl.py list                   the niches defined
    python gl.py tag RTS                check a tag exists and how big it is
    python gl.py audit drone-rts        measure how clean the population is
    python gl.py cache                  what has been fetched so far
"""

import argparse
import json
import os
import sys
import webbrowser

from greenlight import analyze, collect, render, sources, store

ROOT = os.path.dirname(os.path.abspath(__file__))


def load_niches(path=None):
    path = path or os.path.join(ROOT, "config", "niche.json")
    with open(path, encoding="utf-8") as fh:
        config = json.load(fh)
    return config.get("niches") or {}


def cmd_list(args):
    for key, niche in sorted(load_niches(args.config).items()):
        print("%-14s %s" % (key, niche.get("name", "")))
        since = (niche.get("sample_released_since")
                 or niche.get("released_since") or "-")
        print("%-14s require=%s any=%s sample-since=%s cap=%s"
              % ("", niche.get("require_tags"), niche.get("any_tags") or "-",
                 since, niche.get("sample_cap")))
    return 0


def cmd_tag(args):
    """Check a tag before building a niche around it."""
    cache = store.Cache()
    try:
        found = sources.tag(args.name, cache=cache)
    except sources.UnknownTag as exc:
        print("NOT A TAG: %s" % exc)
        return 1
    finally:
        cache.close()
    ordered = sorted(found.values(),
                     key=lambda v: (v.get("positive") or 0) + (v.get("negative") or 0),
                     reverse=True)
    print("%s: %d apps" % (args.name, len(found)))
    print("biggest by review count:")
    for app in ordered[:8]:
        reviews = (app.get("positive") or 0) + (app.get("negative") or 0)
        print("  %-42s %8s reviews" % ((app.get("name") or "?")[:42],
                                       format(reviews, ",")))
    return 0


def cmd_niche(args):
    log = (lambda m: None) if args.quiet else (lambda m: print(m))
    niches = load_niches(args.config)
    niche = niches.get(args.key)
    if niche is None:
        print("No niche %r. Known: %s" % (args.key, ", ".join(sorted(niches))))
        return 1
    if args.cap:
        niche = dict(niche, sample_cap=args.cap)

    cache = store.Cache()
    log("Niche: %s" % niche.get("name"))
    try:
        population, apps, rejected = collect.build(niche, cache, log=log)
    except sources.UnknownTag as exc:
        print("\nERROR: %s" % exc)
        return 1
    finally:
        cache.close()

    log("Population %d games; detail sample %d (%s)"
        % (len(population), len(apps),
           ", ".join("%s: %d" % kv for kv in sorted(rejected.items()))
           or "nothing rejected"))
    if not population:
        print("Nothing matched. Loosen the niche in config/niche.json.")
        return 1

    summary = analyze.summarise(population, apps, niche)
    path = render.render(population, apps, summary, niche)
    log("Wrote %s" % path)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump({"summary": summary, "population": population,
                       "sample": apps}, fh, indent=1, default=str)
        log("Wrote %s" % args.json)
    if not args.quiet:
        print_summary(summary)
    if args.open:
        webbrowser.open("file:///" + path.replace("\\", "/"))
    return 0


def money(value):
    if value is None:
        return "-"
    if value >= 1000000:
        return "$%.1fM" % (value / 1000000.0)
    if value >= 1000:
        return "$%dk" % round(value / 1000.0)
    return "$%d" % round(value)


def print_summary(s):
    rev = s["revenue"]
    print()
    print("=" * 68)
    print(s["niche"])
    print("=" * 68)
    print("%d games in the niche, %d of them paid (detail sample: %d)"
          % (s["population"], rev.get("n", 0), s["sample"]))
    since = s.get("sample_released_since")
    if since:
        print("Population spans ALL release years; the %d-game detail sample is "
              "%s+ only." % (s["sample"], since))
    if not rev.get("n"):
        return
    print()
    print("ESTIMATED NET REVENUE, lifetime (wide error bars - see the report)")
    for label in ("p10", "p25", "median", "p75", "p90", "max"):
        print("  %-8s %s" % (label, money(rev.get(label))))
    print()
    print("  %d of %d earned under $10k" % (rev["under_10k"], rev["n"]))
    print("  %d of %d earned under $50k" % (rev["under_50k"], rev["n"]))
    print("  top 10%% of games took %.0f%% of all revenue in the niche"
          % (rev["top_decile_share"] * 100))

    if s.get("random_slice"):
        print()
        print("A RANDOM 12 FROM THE POPULATION (what the niche actually contains)")
        for a in s["random_slice"]:
            label = ("free-to-play" if a["estimate"].get("free")
                     else money(a["estimate"].get("revenue_mid")))
            print("  %-42s %7s reviews  %s"
                  % ((a.get("name") or "?")[:42],
                     format(a.get("total_reviews") or 0, ","), label))
        print("  If names here look wrong for your niche, the tag filter is too "
              "loose - fix config/niche.json.")

    if s.get("thresholds"):
        print()
        print("REVIEW COUNT AT EACH OUTCOME")
        for label, row in s["thresholds"].items():
            print("  %-12s %6s reviews  %-9s %s"
                  % (label, format(row["reviews"], ","), money(row["revenue"]),
                     (row["name"] or "")[:30]))

    if s.get("prices"):
        print()
        print("PRICE BANDS")
        for row in s["prices"]:
            print("  %-10s %3d games  median %s"
                  % (row["band"], row["n"], money(row["median_revenue"])))

    if s.get("tags"):
        print()
        print("TAGS THAT TRACK WITH REVENUE (top %d games only)" % s["sample"])
        for row in s["tags"][:6]:
            print("  %-26s %4.1fx  (%d games)" % (row["tag"][:26], row["vs_niche"], row["n"]))
        print("  ...")
        for row in s["tags"][-3:]:
            print("  %-26s %4.1fx  (%d games)" % (row["tag"][:26], row["vs_niche"], row["n"]))

    if s.get("reception"):
        r = s["reception"]
        print()
        print("RECEPTION: median %.0f%% positive, %.0f%% of games above 80%%"
              % (r["median_positive"] * 100, r["share_above_80"] * 100))
    print()


def cmd_audit(args):
    """Enrich a RANDOM sample of the population and report what is really in it.

    The population is every app carrying the right tags, and "app" includes DLC,
    soundtracks and off-theme games that happen to share a tag. None of that can
    be filtered without a per-game request, so the honest thing is to measure the
    contamination rather than assume it away. A random sample is the only kind
    that can: the top-N detail pass under-counts DLC, because DLC rarely sits at
    the top of a niche by review count.
    """
    from greenlight import analyze
    log = (lambda m: None) if args.quiet else (lambda m: print(m))
    niches = load_niches(args.config)
    niche = niches.get(args.key)
    if niche is None:
        print("No niche %r." % args.key)
        return 1

    cache = store.Cache()
    try:
        pool = collect.candidates(niche, cache, log=log)
        population = [collect.population_record(a, s) for a, s in pool.items()]
        population = [p for p in population
                      if p["total_reviews"] >= (niche.get("min_reviews") or 0)]
        picked = analyze.random_slice(population, args.n, seed=args.seed)
        log("Auditing %d random games out of %d" % (len(picked), len(population)))

        verdicts = {}
        years = []
        for i, record in enumerate(picked, 1):
            enriched = collect.enrich(str(record["appid"]),
                                      pool.get(str(record["appid"])) or {}, cache)
            if enriched is None:
                verdicts["not a game (DLC, soundtrack, demo)"] =                     verdicts.get("not a game (DLC, soundtrack, demo)", 0) + 1
                continue
            if enriched.get("release_year"):
                years.append(enriched["release_year"])
            ok, why = collect.keeps(enriched, niche)
            key = "kept" if ok else why
            verdicts[key] = verdicts.get(key, 0) + 1
            if i % 10 == 0:
                log("  ... %d/%d" % (i, len(picked)))
    finally:
        cache.close()

    total = sum(verdicts.values()) or 1
    print()
    print("POPULATION AUDIT - %s" % niche.get("name"))
    print("=" * 60)
    for key, count in sorted(verdicts.items(), key=lambda kv: -kv[1]):
        print("  %-40s %3d  %5.0f%%" % (key, count, 100.0 * count / total))
    clean = verdicts.get("kept", 0)
    print()
    print("  %.0f%% of the population would survive the full per-game filter."
          % (100.0 * clean / total))
    if years:
        years.sort()
        print("  release years: %d to %d, median %d"
              % (years[0], years[-1], years[len(years) // 2]))
    print()
    print("  Revenue percentiles are computed over the WHOLE population, so")
    print("  they carry this contamination. Treat the shape as solid and the")
    print("  exact figures as approximate to about this margin.")
    return 0


def cmd_cache(args):
    cache = store.Cache()
    print(cache.stats())
    cache.close()
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="gl", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd")

    p = sub.add_parser("niche", help="analyse a niche")
    p.add_argument("key")
    p.add_argument("--config")
    p.add_argument("--cap", type=int, help="override sample_cap")
    p.add_argument("--slice", type=int, default=12,
                   help="how many random population games to show")
    p.add_argument("--json", help="also write the raw analysis here")
    p.add_argument("--open", action="store_true")
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(func=cmd_niche)

    p = sub.add_parser("list", help="niches defined in the config")
    p.add_argument("--config")
    p.set_defaults(func=cmd_list)

    p = sub.add_parser("tag", help="check a Steam tag exists")
    p.add_argument("name")
    p.set_defaults(func=cmd_tag)

    p = sub.add_parser("audit", help="measure how clean a niche population is")
    p.add_argument("key")
    p.add_argument("--config")
    p.add_argument("-n", type=int, default=40, help="how many to sample")
    p.add_argument("--seed", type=int, default=7)
    p.add_argument("-q", "--quiet", action="store_true")
    p.set_defaults(func=cmd_audit)

    p = sub.add_parser("cache", help="what has been fetched")
    p.set_defaults(func=cmd_cache)

    args = ap.parse_args(argv)
    if not getattr(args, "func", None):
        ap.print_help()
        return 1
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
