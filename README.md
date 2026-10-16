# Greenlight

[![numbers checked by docclaims](https://github.com/jhaney0214-sys/greenlight/actions/workflows/docclaims.yml/badge.svg)](https://github.com/jhaney0214-sys/docclaims)

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
python gl.py wishlists 20000 --price 14.99   # units from launch wishlists
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

## Before launch: wishlists to sales

Everything above starts from review counts, and a game that has not launched
has none. What its developer holds is wishlists. `gl.py wishlists` turns a
launch wishlist count into a range of units, from games whose developers or
publishers printed both numbers:

```bash
python gl.py wishlists 20000              # notes/wishlists-2026-10-16.txt
python gl.py wishlists 5000 --price 14.99
```

`data/wishlist_pairs.json` holds 43 rows for 33 games, gathered on
2026-10-15 from developer postmortems, How To Market A Game case studies,
GameDiscoverCo articles and press, each with its link, the source's date and
the sentence the numbers came from. Nothing in it is estimated here. The
range for a new game is.

In the first week after launch (4 to 14 days, 17 first-week pairs) the median
game sold 0.64 units per wishlist and the middle half ran from 0.07 to 1.19.
Each game was held out in turn and the range refitted on the others: the
middle half held the held-out game's real figure 47% of the time. That is the
measured error, and it is about what a fair middle half should do. The first
day (9 games) and first month (8) get their own ranges; the first year has
one published pair and is not fitted.

**These pairs lean hard toward hits, and the output says so.** Nine of the
seventeen first-week games were written up because they sold well, and their
median is 1.19 units per wishlist. The other eight (developers' own devlogs, a
write-up of a flop, survey rows quoted as examples) have a median of 0.05.
Surveys that asked every respondent rather than the hits found a median of
0.20 (GameDiscoverCo's developer surveys of 2020 and 2021, about 50 and 75
games) and GameDiscoverCo's own estimates for 2024-25 launches found 0.15,
falling to 0.10 for games over $10. The command prints those beside the pairs.
Read the survey medians as the centre and the pairs as how wide the outcomes
run: from a few hundredths of a unit per wishlist to more than three.

Price is taken when given, but only two first-week pairs state a price of $10
or more and two state one under it, so no price band is fitted; the
output lists those pairs and GameDiscoverCo's over-$10 figure instead. The
first-year line is the first-week range times GameDiscoverCo's median
year-one multiplier (2.59, or 2.32 under $10 and 2.7 from $10, their own
estimates for about 5,000 2023-25 launches) and is labelled an estimate. That
multiplier's spread is not published, so the first-year range is too narrow.

Three rows are kept in the file but out of every fit: a 1.0 launch whose
wishlist emails Valve never sent, a count of players rather than copies, and
a "10% of wishlists" that may mean conversions only. Three more give no
period and are kept for the record.

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
greenlight/wishlists.py  launch wishlists to units, from published pairs
data/wishlist_pairs.json the pairs, each with a link, a date and a quote
tests/                 97 tests
tools/docclaims.py     vendored docclaims v0.3.3; checks claims.json against the source
tools/recent.py        releases since a year, including those under min_reviews
tools/validate.py      the copies estimate against 193 games whose real sales are known
```

---

## What it does not tell you

- **Whether *your* game will sell.** It describes a market, not your execution.
  The gap between the median and the top decile in any niche is mostly craft and
  marketing, and nothing here measures either.
- **Wishlist counts of other games.** Steam does not publish them. Review
  counts at each outcome are the closest public proxy and that is what the
  report gives. Going the other way, from your own wishlists to your sales,
  is `gl.py wishlists` (above), and it rests on published pairs that lean
  heavily toward hits.
- **Anything about unreleased competitors.** Coming-soon titles are dropped for
  lack of data, so a niche can be more crowded than it looks.
- **Causation from tags.** A tag on the games that earn more may be riding on
  them rather than driving them.
- **That the dollar figures are right.** Half of the model has now been
  checked and half has not.
  **Reviews to copies, checked 2026-10-13** against GameDiscoverCo's October
  2022 survey: 193 paid games with the review count beside the lifetime units
  from the developer's own Steam back end (`python tools/validate.py`, output
  in `notes/validation-2026-10-13.txt`). Over all of them the estimate is 19%
  low at the median. For games released 2020 to 2022 with under 1,000 reviews
  (90 games, the part of the survey most like a new indie release) the median
  estimate is 1% low, so a niche's median is about where the report puts it.
  **A single game is another matter.** The report's low-to-high range, the
  estimate minus and plus 40%, held the real figure for 48% of games; 71% were
  within a factor of two. Games with 1,000 to 9,999 reviews sold about half
  again what is estimated (median estimate 33% low), so a niche's top quarter
  is probably understated. Under 30 reviews the estimate ran 21% high and a
  quarter of those games sold a third of it or less.
  Limits of the check: the survey is developers who answered a newsletter,
  it ends in 2022, and the multiplier used for 2024 and later (25) is outside
  it.
  **Copies to dollars is still unchecked, and on 2026-10-13 no public data
  was found to check it with.** The survey has no prices, and two searches
  for a set of games with units, gross and price together found none. What
  exists is other calculators' own assumptions: structural deductions (tax
  and refunds, regional prices about a fifth under the US price, Steam's 30%)
  that put a developer's take at 41 to 55 percent of list price a copy. The
  two 0.62 factors here come to 38 percent, a little under that range, so if
  those calculators are right the dollar figures run low, not high. That is
  one unmeasured number set beside others, and it is not a check.
- **Anything about eras.** `Military`, `War` and `Wargame` catch every period, so
  a "modern-military" niche is really "military, all eras" — it contains
  medieval and world-war titles. Fine as a comparison set for RTS buyers,
  misleading if read literally.
