"""Turning review counts into money, with the error bars left visible.

Steam publishes review counts and nothing else. The whole indie industry
estimates sales from them using the Boxleiter method - sales are some multiple
of reviews - and that multiple has fallen steadily as leaving reviews became
normal. A 2013 game might see one review per sixty copies; a 2024 one nearer
one per thirty.

This is a heuristic, not a measurement, and it is wrong for any individual game:
a title with a review-begging prompt or a brigading controversy sits far off the
line. It is used here because it is directionally reliable across a *population*,
which is the only claim this tool makes. Every figure it produces is labelled an
estimate, and the report shows the range rather than a single number, because
the last project taught expensively what happens when an estimate gets displayed
with the same confidence as a fact.

A second, independent estimate comes free: SteamSpy publishes an owner band per
app. Where the two disagree badly, that disagreement is the honest error bar and
is surfaced rather than averaged away.
"""

# Reviews per copy sold, by release year. Falling, because reviewing got normal.
# These are the community's consensus ranges, not measurements of anything.
MULTIPLIER_BY_ERA = (
    (2013, 70.0),
    (2016, 55.0),
    (2019, 45.0),
    (2021, 35.0),
    (2023, 30.0),
    (9999, 25.0),
)

# How much of list price a copy actually earns over a lifetime: launch discounts,
# seasonal sales, regional pricing and bundles all pull it down.
EFFECTIVE_PRICE_FACTOR = 0.62

# Steam takes 30% under 10M gross. Refunds, chargebacks and VAT take more.
PLATFORM_AND_TAX_FACTOR = 0.62

# The multiplier is uncertain by roughly this much either way.
MULTIPLIER_SPREAD = 0.4


def review_multiplier(year):
    """Copies sold per review, for a game released in `year`."""
    if not year:
        return 35.0
    for cutoff, multiplier in MULTIPLIER_BY_ERA:
        if year <= cutoff:
            return multiplier
    return 25.0


def estimate_sales(reviews, year):
    """(low, mid, high) copies sold. None when there is nothing to work from."""
    if not reviews:
        return None
    mid = reviews * review_multiplier(year)
    return (mid * (1 - MULTIPLIER_SPREAD), mid, mid * (1 + MULTIPLIER_SPREAD))


def owners_band(raw):
    """SteamSpy's owner range, '2,000,000 .. 5,000,000', as (low, high)."""
    if not raw or ".." not in str(raw):
        return None
    try:
        low, high = str(raw).split("..")
        return (int(low.strip().replace(",", "")),
                int(high.strip().replace(",", "")))
    except (ValueError, AttributeError):
        return None


def net_revenue(copies, price_cents):
    """What the developer plausibly kept, in dollars."""
    if not copies or not price_cents:
        return 0.0
    return (copies * (price_cents / 100.0)
            * EFFECTIVE_PRICE_FACTOR * PLATFORM_AND_TAX_FACTOR)


def estimate(app):
    """Attach sales and revenue estimates to one app record.

    Returns a dict with a mid estimate, a range, and - where SteamSpy's owner
    band is available - how far that independent figure disagrees. Disagreement
    is information, not noise.
    """
    reviews = app.get("total_reviews") or 0
    year = app.get("release_year")
    price = app.get("price_cents") or 0

    sales = estimate_sales(reviews, year)
    if sales is None:
        return {"known": False, "reason": "no reviews"}

    low, mid, high = sales
    out = {
        "known": True,
        "multiplier": review_multiplier(year),
        "sales_low": low,
        "sales_mid": mid,
        "sales_high": high,
        "revenue_low": net_revenue(low, price),
        "revenue_mid": net_revenue(mid, price),
        "revenue_high": net_revenue(high, price),
        "free": price == 0,
    }

    band = owners_band(app.get("owners"))
    if band:
        owners_mid = (band[0] + band[1]) / 2.0
        out["owners_mid"] = owners_mid
        # Free games have owners far above sales by definition, so the
        # comparison only means something for paid ones.
        if owners_mid > 0 and price > 0:
            out["owners_vs_reviews"] = owners_mid / mid
    return out


def confidence(app, est):
    """How much to trust one app's estimate: 'good', 'fair' or 'poor'."""
    if not est.get("known"):
        return "poor"
    reviews = app.get("total_reviews") or 0
    if reviews < 30:
        # Below this the multiplier is meaningless - a handful of reviews says
        # nothing about how many copies moved.
        return "poor"
    ratio = est.get("owners_vs_reviews")
    if ratio is not None and (ratio < 0.4 or ratio > 3.0):
        # The two independent estimates disagree by more than 2.5x.
        return "fair"
    return "good" if reviews >= 100 else "fair"
