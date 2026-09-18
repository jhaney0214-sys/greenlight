# Greenlight

**Status: production.** One-shot analysis tool, no state to rot. See [PRODUCTION.md](../PRODUCTION.md).

Market evidence for a game before you build it. Enumerates every title in a
niche from Steam's own public data, estimates what each one earned, and reports
**the distribution rather than the average** — because Steam revenue is a power
law and an average across it describes no game that exists.

No third-party packages. No API keys. No paid data.

```bash
python gl.py niche drone-rts --open
```

---

## Why the distribution and not the average

Ask "how much does an RTS make on Steam" and any average will flatter you,
because a handful of titles take nearly everything. In the modern-military RTS
niche the top decile takes **88% of all revenue**. The mean is a number about
Hearts of Iron IV; the median is a number about you.

So the report is percentiles, counts and shares. There is no mean anywhere in it.

---

## Read the random slice first

The report lists the biggest games in a niche, and contamination never sits at
the top — it sits near the median, where nothing was showing it. So the report
now opens with **twelve games drawn at random from the population**, seeded so
re-running shows the same twelve.

That section immediately earned its place. A "modern-military RTS" niche turned
out to contain **Laptop Tycoon**, because it carries `RTS` and `Modern` — and
`Modern` means modern *setting*, not modern *military*. The tag filter was doing
exactly what it was told; what it was told was wrong. Dropping `Modern` from
`any_tags` took the niche from 717 games to 546.

If the names in that slice look wrong for your niche, every number on the page is
about the wrong set of games. That is the first thing to check and the cheapest.

## Measure the contamination rather than assuming it away

```bash
python gl.py audit drone-rts
```

The population is every app carrying the right tags, and "app" includes DLC and
soundtracks. None of that can be filtered without a request per game, so `audit`
enriches a **random** sample and reports what is really in there:

```
POPULATION AUDIT - Modern-military RTS (the Drone Command niche)
  kept                                      27     68%
  older than 2016                           12     30%
  not a game (DLC, soundtrack, demo)         1      2%

  release years: 2006 to 2026, median 2020
```

A random sample is the only kind that can answer this — the top-N detail pass
under-counts DLC, because DLC rarely sits at the top of a niche by review count.
Measured here, DLC contamination is about 2%, and nothing failed the theme
filter once `Modern` was removed.

## The two mistakes this tool is built to avoid

Both are the same failure — a number that looks authoritative and is quietly
about something else — and both were live bugs here before they were guards.

### SteamSpy answers unknown tags with junk

Ask for a tag that does not exist and SteamSpy does not return an error. It
returns a fixed list of seventy unrelated games headed by Grand Theft Auto IV.
`Drones` is not a Steam tag. Neither is `Real Time Strategy` — the real one is
`RTS`. Analyse either and you get confident numbers about GTA IV.

Greenlight fingerprints that response and raises instead:

```bash
$ python gl.py tag Drones
NOT A TAG: Steam has no tag 'Drones' - SteamSpy answered with its junk
fallback. Check the exact spelling on a store page.
```

Check a tag before building a niche around it. `gl.py tag RTS` shows the size and
the biggest titles carrying it.

### Ranking before taking a median

The first working version enumerated a niche, ranked by review count, kept the
top 25 and reported the median. That median came out at **$110M**, and the
"median game in the niche" was Age of Empires II. Every number was survivorship
bias with a decimal point.

The fix is two passes with different jobs, and the report never confuses them:

| pass | covers | used for |
|---|---|---|
| **population** | every game matching the tag logic | revenue distribution, prices, reception |
| **sample** | the biggest N, enriched | tags, release cadence — labelled "top N only" |

The population pass costs nothing extra: SteamSpy's tag response already carries
review counts and prices for all of them. Only per-game detail — release dates
and tag votes — needs a request each, and that is the only thing the biased
slice is allowed to answer.

---

## Defining a niche

`config/niche.json`. Tags are Steam's own and are fussy about spelling.

**A misspelled tag is refused, not analysed.** The tags in this file are a
hand-written claim about a vocabulary Valve controls, and asking SteamSpy for a
tag that does not exist gets you a silent junk list or a silent nothing rather
than an error. `sources.tag` catches both and raises `UnknownTag` naming the
spelling, so `require_tags` and `any_tags` stop the run rather than reporting a
market that is not there.

`exclude_tags` is the one exception and it is deliberate: a misspelled
exclusion excludes nothing, which is harmless, so it logs
`! exclude tag 'x' does not exist, skipped` and carries on.

> **Correction, 2026-09-18.** This section said the opposite on 2026-09-17 -
> that a misspelled tag silently reports an empty market, which would invert
> the tool's whole output. That was wrong. `UnknownTag` and the junk-list
> detector have been in `sources.py` since the **initial commit**; the claim
> was reasoned from the shape of the SteamSpy API rather than read off the
> code, written straight into this README as a known limitation, and left
> there for a day. Verified this time by stubbing `sources.tag` to raise on
> `"Real Time Strategy"` and running `collect.candidates` for each of the
> three tag fields, with a positive control first so a dead probe could not
> pass as a clean result.

```json
"drone-rts": {
  "name": "Modern-military RTS (the Drone Command niche)",
  "require_tags": ["RTS"],
  "any_tags": ["Military", "War", "Wargame"],
  "exclude_tags": ["Anime", "Fantasy", "Nudity", "Sexual Content"],
  "sample_released_since": 2016,
  "min_reviews": 10,
  "sample_cap": 180
}
```

| field | meaning |
|---|---|
| `require_tags` | must carry **all** of these. One or two. |
| `any_tags` | and **at least one** of these. The theme filter. |
| `exclude_tags` | drop anything carrying these. |
| `min_reviews` | below this a game tells you nothing. |
| `sample_cap` | how many to enrich. About three seconds each on a cold cache. |
| `sample_released_since` | **named for its scope.** Release dates only exist after the per-game pass, so this filters the detail sample and *not* the population the revenue figures come from. The report says so on the page. |

All the filtering happens through tag queries, so it applies to the whole
population rather than a sample.

---

## Commands

```bash
python gl.py list                 # niches defined
python gl.py tag RTS              # check a tag exists, see its biggest games
python gl.py niche drone-rts      # analyse, write out/index.html
python gl.py niche drone-rts --cap 40 --json out/analysis.json
python gl.py audit drone-rts      # measure how clean the population is
python gl.py cache                # what has been fetched
python -m unittest discover -s tests
```

Everything is cached in sqlite. A cold run over a few hundred games takes about
ten minutes; the same run again is instant.

---

## How the money is estimated

Steam publishes review counts and nothing else, so:

```
copies  ≈ reviews × era multiplier (70 in 2013 falling to 25 today)
revenue ≈ copies × price × 0.62 effective price × 0.62 after Steam's cut and tax
```

The multiplier falls over time because leaving reviews became normal. This is
the Boxleiter method the indie industry uses, and it is **a heuristic, not a
measurement** — wrong for any individual game, directionally reliable across a
population. That is the only claim made here.

A second, independent estimate comes free: SteamSpy publishes an owner band per
game. Where the two disagree by more than 2.5×, the row is marked `fair` instead
of `good` rather than averaging the disagreement away. Under 30 reviews it is
marked `poor`, because a handful of reviews says nothing about copies sold.

Every figure in the report is labelled an estimate, and the report leads with
that rather than burying it.

---

## Layout

```
gl.py                  CLI
config/niche.json      what counts as your niche   <- edit this
greenlight/sources.py  Steam and SteamSpy, with the junk-tag guard
greenlight/collect.py  population and sample passes
greenlight/revenue.py  the estimation model and its error bars
greenlight/analyze.py  percentiles, tags, prices, cadence
greenlight/render.py   one self-contained HTML page
greenlight/store.py    sqlite cache
tests/                 58 tests
```

---

## What it does not tell you

- **Whether *your* game will sell.** It describes a market, not your execution.
  The gap between the median and the top decile in any niche is mostly craft and
  marketing, and nothing here measures either.
- **Wishlist counts.** Steam does not publish them. Review counts at each
  outcome are the closest public proxy and that is what the report gives.
- **Anything about unreleased competitors.** Coming-soon titles are dropped for
  lack of data, so a niche can be more crowded than it looks.
- **Causation from tags.** A tag on the games that earn more may be riding on
  them rather than driving them.
- **That the revenue model is right.** It has never been checked against a game
  with publicly disclosed sales. The distribution's *shape* — power law, brutal
  median, price bands mattering enormously — is robust to the multiplier being
  off. The dollar figures are not. This is the largest remaining gap.
- **Anything about eras.** `Military`, `War` and `Wargame` catch every period, so
  a "modern-military" niche is really "military, all eras" — it contains
  medieval and world-war titles. Fine as a comparison set for RTS buyers,
  misleading if read literally.
