"""Talking to Steam and SteamSpy.

Three free, keyless endpoints carry the whole tool:

  * steamspy.com/api.php?request=tag   - every app carrying a tag, with owner
    bands, review counts and price. This is how a niche gets enumerated.
  * steamspy.com/api.php?request=appdetails - per-app tag votes, which is what
    makes tag correlation possible at all.
  * store.steampowered.com/api/appdetails and /appreviews - release date, type
    (so DLC can be dropped) and the authoritative review count.

Everything is cached in sqlite, because a niche of 300 games is 600 requests and
nobody should pay that twice.

The junk-response trap
----------------------
SteamSpy does not return an error for a tag that does not exist. It returns a
fixed list of 70 unrelated apps headed by Grand Theft Auto IV. Ask it for
"Drones" or "Real Time Strategy" - neither is a real Steam tag - and you get
that, silently, and every number downstream is quietly about GTA IV. It is
detected here and raised as an error, because a wrong answer that looks right is
the single most expensive thing this kind of tool can do.
"""

import json
import time
import urllib.error
import urllib.parse
import urllib.request

USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36")

STEAMSPY = "https://steamspy.com/api.php"
STEAM_APP = "https://store.steampowered.com/api/appdetails"
STEAM_REVIEWS = "https://store.steampowered.com/appreviews/%d"

# SteamSpy asks for one request a second. Steam's store API tolerates roughly
# 200 per five minutes. Both are free and neither owes us anything, so the
# defaults here are deliberately slower than the stated ceilings.
STEAMSPY_INTERVAL = 1.1
STEAM_INTERVAL = 1.6

TIMEOUT = 30

# The fingerprint of SteamSpy's "no such tag" response.
JUNK_TAG_SIZE = 70
JUNK_TAG_MARKER = "Grand Theft Auto IV"


class SourceError(Exception):
    pass


class UnknownTag(SourceError):
    """The tag does not exist on Steam. SteamSpy will not say so itself."""


_last_call = {}


def _throttle(host, interval):
    now = time.time()
    wait = _last_call.get(host, 0) + interval - now
    if wait > 0:
        time.sleep(wait)
    _last_call[host] = time.time()


def _get(url, host, interval):
    _throttle(host, interval)
    req = urllib.request.Request(url, headers={
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read()
    except Exception as exc:
        raise SourceError("%s: %s" % (url, exc)) from exc
    try:
        return json.loads(raw.decode("utf-8", "replace"))
    except ValueError as exc:
        raise SourceError("%s: bad JSON" % url) from exc


def looks_like_junk_tag(payload):
    """True when SteamSpy has silently answered a tag it does not know.

    Both halves of the test matter. The size alone would condemn a real tag that
    happens to have seventy games; the marker alone would condemn a legitimate
    query that genuinely contains Grand Theft Auto IV. Together they are the
    fingerprint of the fallback list.

    Every entry is checked rather than just the first: relying on the junk
    always arriving in the same order is a bet on JSON key ordering that costs
    nothing to avoid.
    """
    if not isinstance(payload, dict) or len(payload) != JUNK_TAG_SIZE:
        return False
    return any(JUNK_TAG_MARKER in ((value or {}).get("name") or "")
               for value in payload.values())


def tag(name, cache=None, max_age=7 * 86400):
    """Every app carrying `name`, keyed by appid.

    Raises UnknownTag rather than returning SteamSpy's junk fallback. Tag names
    are Steam's own and are fussy: "RTS" works, "Real Time Strategy" does not,
    and "Base-Building" is hyphenated while "Strategy RPG" is not.
    """
    url = "%s?request=tag&tag=%s" % (STEAMSPY, urllib.parse.quote(name))
    payload = _cached(cache, url, max_age, lambda: _get(url, "steamspy", STEAMSPY_INTERVAL))

    # SteamSpy has two ways of saying "no such tag" and neither is an error.
    # Sometimes it is the seventy-game junk list; sometimes it is simply empty.
    # "Real Time Strategy" returns the second and reported cleanly as "0 apps"
    # until this was added - a silent nothing, which is the same failure as a
    # silent something.
    if looks_like_junk_tag(payload):
        if cache is not None:
            cache.forget(url)
        raise UnknownTag(
            "Steam has no tag %r - SteamSpy answered with its junk fallback. "
            "Check the exact spelling on a store page." % name)
    if not payload:
        if cache is not None:
            cache.forget(url)
        raise UnknownTag(
            "Steam has no tag %r - SteamSpy returned nothing at all. Check the "
            "exact spelling on a store page (the RTS tag is 'RTS', not "
            "'Real Time Strategy')." % name)
    return payload


def app_tags(appid, cache=None, max_age=30 * 86400):
    """SteamSpy's per-app record, including tag vote counts."""
    url = "%s?request=appdetails&appid=%d" % (STEAMSPY, appid)
    return _cached(cache, url, max_age,
                   lambda: _get(url, "steamspy", STEAMSPY_INTERVAL)) or {}


def app_details(appid, cache=None, max_age=30 * 86400):
    """Steam's own record: type, release date, genres, current price."""
    url = ("%s?appids=%d&cc=us&l=en&filters=basic,price_overview,release_date,"
           "genres,categories,developers,publishers" % (STEAM_APP, appid))
    payload = _cached(cache, url, max_age,
                      lambda: _get(url, "steam", STEAM_INTERVAL))
    entry = (payload or {}).get(str(appid)) or {}
    if not entry.get("success"):
        return {}
    return entry.get("data") or {}


def app_reviews(appid, cache=None, max_age=7 * 86400):
    """The authoritative review counts, which SteamSpy's own figures lag."""
    url = (STEAM_REVIEWS % appid) + ("?json=1&num_per_page=0&language=all"
                                     "&purchase_type=all&review_type=all")
    payload = _cached(cache, url, max_age,
                      lambda: _get(url, "steam", STEAM_INTERVAL))
    return (payload or {}).get("query_summary") or {}


def _cached(cache, url, max_age, fetch):
    if cache is None:
        return fetch()
    hit = cache.get(url, max_age)
    if hit is not None:
        return hit
    value = fetch()
    cache.put(url, value)
    return value
