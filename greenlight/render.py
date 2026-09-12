"""One self-contained HTML page. No assets, no CDN, light and dark."""

import html
import os
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_PATH = os.path.join(ROOT, "out", "index.html")

CSS = """
:root{--bg:#f6f7f9;--card:#fff;--ink:#14171c;--muted:#5d6672;--line:#e3e6ea;
--accent:#1f6feb;--good:#0f7b4f;--good-bg:#e3f5ec;--warn:#8a5a00;
--warn-bg:#fdf3dd;--bad:#a11;--chip:#eef1f5;}
@media (prefers-color-scheme: dark){:root:not([data-theme="light"]){
--bg:#0f1216;--card:#171b21;--ink:#e8ecf1;--muted:#98a2b3;--line:#252b33;
--accent:#5aa2ff;--good:#4ade80;--good-bg:#10291d;--warn:#f5c451;
--warn-bg:#2a2213;--bad:#f87171;--chip:#212831;}}
:root[data-theme="dark"]{--bg:#0f1216;--card:#171b21;--ink:#e8ecf1;
--muted:#98a2b3;--line:#252b33;--accent:#5aa2ff;--good:#4ade80;
--good-bg:#10291d;--warn:#f5c451;--warn-bg:#2a2213;--bad:#f87171;--chip:#212831;}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);
font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:28px 18px 64px}
h1{margin:0 0 4px;font-size:25px;letter-spacing:-.02em}
h2{font-size:17px;margin:32px 0 10px;letter-spacing:-.01em}
.sub{color:var(--muted);font-size:13px;margin-bottom:8px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:16px 18px;margin-bottom:14px}
.warn{background:var(--warn-bg);border-color:var(--warn);color:var(--ink)}
.warn b{color:var(--warn)}
table{width:100%;border-collapse:collapse;font-size:13.5px}
th{text-align:left;color:var(--muted);font-weight:600;font-size:12px;
text-transform:uppercase;letter-spacing:.05em;padding:6px 8px;
border-bottom:1px solid var(--line)}
td{padding:6px 8px;border-bottom:1px solid var(--line)}
td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
.big{font-size:26px;font-weight:700;letter-spacing:-.02em}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}
.stat{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}
.stat .k{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.05em}
.bar{height:8px;background:var(--chip);border-radius:99px;overflow:hidden;margin-top:6px}
.bar i{display:block;height:100%;background:var(--accent)}
.tag{font-size:11.5px;padding:2px 8px;border-radius:999px;background:var(--chip);
color:var(--muted);white-space:nowrap;display:inline-block}
.tag.good{background:var(--good-bg);color:var(--good)}
.tag.warn{background:var(--warn-bg);color:var(--warn)}
.scroll{overflow-x:auto}
footer{margin-top:34px;color:var(--muted);font-size:12px;line-height:1.7;
border-top:1px solid var(--line);padding-top:14px}
code{background:var(--chip);padding:1px 5px;border-radius:4px;font-size:12px}
"""


def _e(text):
    return html.escape(str(text if text is not None else ""))


def money(value):
    if value is None:
        return "-"
    if value >= 1000000:
        return "$%.1fM" % (value / 1000000.0)
    if value >= 1000:
        return "$%dk" % round(value / 1000.0)
    return "$%d" % round(value)


def _stat(label, value, note=""):
    return ('<div class="stat"><div class="k">%s</div>'
            '<div class="big">%s</div><div class="k">%s</div></div>'
            % (_e(label), _e(value), _e(note)))


def render(population, apps, summary, niche, path=None):
    path = path or OUT_PATH
    rev = summary["revenue"]
    now = datetime.now().astimezone()

    stats = ""
    if rev.get("n"):
        stats = '<div class="grid">%s</div>' % "".join([
            _stat("Median game", money(rev["median"]), "estimated net, lifetime"),
            _stat("Top 10%", money(rev["p90"]), "the good outcome"),
            _stat("Best in niche", money(rev["max"]), "the outlier"),
            _stat("Under $10k", "%d of %d" % (rev["under_10k"], rev["n"]),
                  "%.0f%% of the niche" % (100.0 * rev["under_10k"] / rev["n"])),
        ])

    dist = ""
    if rev.get("n"):
        rows = []
        for label, key in (("10th percentile", "p10"), ("25th", "p25"),
                           ("median", "median"), ("75th", "p75"),
                           ("90th", "p90"), ("best", "max")):
            value = rev.get(key) or 0
            width = 100.0 * value / (rev["max"] or 1)
            rows.append('<tr><td>%s</td><td class="num">%s</td>'
                        '<td style="width:55%%"><div class="bar"><i style="width:%.1f%%">'
                        '</i></div></td></tr>' % (_e(label), money(value), width))
        dist = ('<div class="card"><table>%s</table>'
                '<p class="sub" style="margin-top:10px">The top decile took '
                '<b>%.0f%%</b> of all revenue in this niche. That concentration is '
                'the number that matters: the median is what you should plan for, '
                'not the headline.</p></div>'
                % ("".join(rows), rev["top_decile_share"] * 100))

    # A random slice, shown high in the report. Everything else lists the
    # biggest games, which is exactly where a contaminated niche looks clean.
    slice_html = ""
    if summary.get("random_slice"):
        rows = "".join(
            '<tr><td>%s</td><td class="num">%s</td><td class="num">%s</td></tr>'
            % (_e((a.get("name") or "?")[:46]),
               format(a.get("total_reviews") or 0, ","),
               "free-to-play" if a["estimate"].get("free")
               else money(a["estimate"].get("revenue_mid")))
            for a in summary["random_slice"])
        slice_html = ('<div class="card"><table><tr><th>game</th>'
                      '<th class="num">reviews</th><th class="num">est. net</th>'
                      '</tr>%s</table>'
                      '<p class="sub" style="margin-top:10px">A random draw, not '
                      'the top of the list. <b>If names here look wrong for your '
                      'niche, the tag filter is too loose</b> and every number on '
                      'this page is about the wrong set of games. Fix '
                      '<code>config/niche.json</code> and re-run.</p></div>' % rows)

    scope = ""
    if summary.get("sample_released_since"):
        scope = ('<div class="card"><p class="sub" style="margin:0">'
                 'Release dates only arrive with the per-game pass, so the '
                 '<b>%s+</b> filter applies to the %d-game detail sample only. '
                 'The %d-game population behind the revenue figures spans '
                 '<b>all release years</b>.</p></div>'
                 % (_e(summary["sample_released_since"]), summary["sample"],
                    summary["population"]))

    thresholds = ""
    if summary.get("thresholds"):
        rows = "".join(
            '<tr><td>%s</td><td class="num">%s</td><td class="num">%s</td><td>%s</td></tr>'
            % (_e(label), format(row["reviews"] or 0, ","),
               money(row["revenue"]), _e((row["name"] or "")[:40]))
            for label, row in summary["thresholds"].items())
        thresholds = ('<div class="card"><table><tr><th>outcome</th>'
                      '<th class="num">reviews</th><th class="num">est. net</th>'
                      '<th>example</th></tr>%s</table>'
                      '<p class="sub" style="margin-top:10px">Reviews are the only '
                      'public signal of how a launch went, so these are the concrete '
                      'targets to aim at.</p></div>' % rows)

    prices = ""
    if summary.get("prices"):
        rows = "".join(
            '<tr><td>%s</td><td class="num">%d</td><td class="num">%s</td>'
            '<td class="num">%.0f%%</td></tr>'
            % (_e(r["band"]), r["n"], money(r["median_revenue"]), r["share"] * 100)
            for r in summary["prices"])
        prices = ('<div class="card"><table><tr><th>price</th><th class="num">games</th>'
                  '<th class="num">median net</th><th class="num">share of niche</th></tr>'
                  '%s</table></div>' % rows)

    tags = ""
    if summary.get("tags"):
        top = summary["tags"][:12]
        bottom = summary["tags"][-6:]
        def tagrows(rows):
            return "".join(
                '<tr><td>%s</td><td class="num">%d</td><td class="num">%s</td>'
                '<td class="num"><span class="tag %s">%.1fx</span></td></tr>'
                % (_e(r["tag"]), r["n"], money(r["median_revenue"]),
                   "good" if (r["vs_niche"] or 0) >= 1.3 else
                   ("warn" if (r["vs_niche"] or 0) < 0.8 else ""),
                   r["vs_niche"] or 0)
                for r in rows)
        tags = ('<div class="card"><table><tr><th>tag</th><th class="num">games</th>'
                '<th class="num">median net</th><th class="num">vs niche</th></tr>'
                '%s<tr><td colspan="4" class="sub">...</td></tr>%s</table>'
                '<p class="sub" style="margin-top:10px">A tag on the games that earn '
                'more is not proof it causes anything - popular tags ride on popular '
                'games. It is a signal about what this audience browses for, and tags '
                'are a launch decision you live with.</p></div>'
                % (tagrows(top), tagrows(bottom)))

    cadence = ""
    if summary.get("cadence"):
        rows = "".join(
            '<tr><td>%s</td><td class="num">%d</td><td class="num">%s</td></tr>'
            % (r["year"], r["n"], money(r["median_revenue"]))
            for r in summary["cadence"])
        cadence = ('<div class="card"><table><tr><th>year</th>'
                   '<th class="num">releases in sample</th>'
                   '<th class="num">median net</th></tr>%s</table></div>' % rows)

    top_rows = "".join(
        '<tr><td>%s</td><td class="num">%s</td><td class="num">%s</td>'
        '<td class="num">%s</td><td class="num">%s</td><td>%s</td></tr>'
        % (_e(a["name"][:44]), a.get("release_year") or "-",
           "$%.0f" % ((a.get("price_cents") or 0) / 100.0) if not a["estimate"].get("free") else "free",
           format(a.get("total_reviews") or 0, ","),
           money(a["estimate"].get("revenue_mid")),
           '<span class="tag %s">%s</span>' % (
               "good" if a["confidence"] == "good" else
               ("warn" if a["confidence"] == "poor" else ""), a["confidence"]))
        for a in apps[:30])

    doc = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Greenlight</title><style>%s</style></head><body><div class="wrap">
<h1>%s</h1>
<div class="sub">%d games in the niche &middot; generated %s &middot;
data from Steam and SteamSpy</div>

<div class="card warn">
<b>Every revenue figure here is an estimate.</b> Steam publishes review counts and
nothing else, so sales are inferred from reviews using the multiplier the indie
industry uses, and revenue from that. It is directionally reliable across a
population and wrong for any individual game. Use the shape of the distribution,
not any single number. The <code>confidence</code> column flags rows where the
two independent estimates disagree or the review count is too small to mean much.
</div>

%s

%s

<h2>What is actually in this niche</h2>
%s

<h2>What the money actually looks like</h2>
%s

<h2>Reviews you would need</h2>
%s

<h2>What the niche charges</h2>
%s

<h2>Tags <span class="sub">(top %d games only)</span></h2>
%s

<h2>How crowded it is getting <span class="sub">(top %d games only)</span></h2>
%s

<h2>The biggest games in this niche</h2>
<div class="card scroll"><table><tr><th>game</th><th class="num">year</th>
<th class="num">price</th><th class="num">reviews</th><th class="num">est. net</th>
<th>confidence</th></tr>%s</table></div>

<footer>
Sales estimated as reviews &times; an era-adjusted multiplier (%s), revenue as
sales &times; price &times; 0.62 effective price &times; 0.62 after Steam's cut
and tax. Owner bands from SteamSpy give a second, independent estimate; where the
two disagree by more than 2.5&times; the row is marked <code>fair</code> rather
than <code>good</code>. Niche defined in <code>config/niche.json</code>.
</footer>
</div></body></html>""" % (
        CSS, _e(summary.get("niche") or "Niche"), summary["population"],
        now.strftime("%Y-%m-%d %H:%M"), stats, scope, slice_html, dist,
        thresholds, prices,
        summary["sample"], tags, summary["sample"], cadence, top_rows,
        "25 to 70 by year")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return path
