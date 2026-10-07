"""Player pages that share (Wave I-P, IP-5; docs/SECURITY_PUBLIC.md § 15).

``/player/<gsis>`` unfurled as the site's default card. The page shell (``main.web``) now asks ``shell`` for the player's
own title and description, and the sitemap (``blog.sitemap``) asks ``top`` for the 200 highest projections:

* **From what this process already holds, and nothing else.** The one source is the matchup board's week frame for the
  default scoring (``matchup_board._cache``: one row per player with a game this week — projection, 80 % range, team,
  opponent, kickoff — built when anyone opens the matchup board or the player screens browsing). A crawler's hit reads
  that region's keys and one entry: no database query, no provider call, nothing scheduled or built. Not held (a
  restarted server, the 10 minutes passed, nobody browsed) → the default card / no player in the sitemap.
* **The default scoring** is ``refleague.DEFAULT`` (Half PPR); its key is computed only when the reference scorings are
  already loaded (``refleague._scorings``) — never read for a crawler.
* **Ids** must ``fullmatch`` ``^00-\\d{7}$`` (the gsis pattern of the free calculator); anything else is the default
  card. Every text goes through ``blog.seo_tags`` (escaped like the rest of the shell). The rank at the position is
  computed once per held frame (a dict of at most one frame).
* ``noindex``: a page whose query string names a league (``?league=``) gets ``X-Robots-Tag: noindex`` and a robots meta
  tag — a league's pages are not for search engines (``main.web``).

Words: docs/WORDS.md § "Player pages that share (Wave I-P, IP-5)".
"""

from __future__ import annotations

import math
import re
import threading
from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from . import blog, matchup_board, refleague
from .settings import APP_NAME

GSIS = re.compile(r"^00-\d{7}$")
PATH = re.compile(r"^/?player/(00-\d{7})/?$")
SITEMAP_TOP = 200
POSITION_WORDS = {"QB": "quarterbacks", "RB": "running backs", "WR": "wide receivers", "TE": "tight ends"}
ET = ZoneInfo("America/New_York")
ROBOTS_META = '<meta name="robots" content="noindex" />'

_lock = threading.Lock()
_ranked: dict[int, tuple[Any, dict[str, int], dict[str, int]]] = {}     # id(frame) -> (frame, rank, n at position)


def _default_key() -> str | None:
    """The default scoring's key as the research memo spells it, or None while the reference scorings are not loaded."""
    if not refleague._scorings:          # noqa: SLF001 - held or not: never read for a crawler
        return None
    try:
        from league_lab import anyleague as A
        sc = refleague.scoring_of(refleague.shape(refleague.DEFAULT))
        return A._scoring_key({k: float(v) for k, v in sc.items() if v is not None})   # noqa: SLF001
    except Exception:  # noqa: BLE001 - anything odd: the default card
        return None


def held_frame() -> pd.DataFrame | None:
    """This week's board in the default scoring, if this process holds it (the newest week held); else None."""
    want = _default_key()
    if want is None:
        return None
    best: tuple | None = None
    for k in matchup_board._cache.keys():                                                   # noqa: SLF001
        if (isinstance(k, tuple) and len(k) == 5 and k[0] == "board" and isinstance(k[1], tuple) and len(k[1]) >= 2
                and k[1][0] == "priced" and k[1][1] == want and k[4] is False):
            if best is None or (k[2], k[3]) > (best[2], best[3]):
                best = k
    if best is None:
        return None
    df = matchup_board._cache.get(best)                                                     # noqa: SLF001
    if df is None or df.empty or "proj_points" not in df:
        return None
    df.attrs.setdefault("ip5_week", (int(best[2]), int(best[3])))
    return df


def _ranks(df: pd.DataFrame) -> tuple[dict[str, int], dict[str, int]]:
    """{gsis: rank at his position by projection (1 = highest; ties share the better rank)}, {position: players ranked}."""
    with _lock:
        hit = _ranked.get(id(df))
        if hit is not None and hit[0] is df:
            return hit[1], hit[2]
    p = pd.to_numeric(df["proj_points"], errors="coerce")
    ok = p.notna() & df["position"].isin(list(POSITION_WORDS))
    r = p[ok].groupby(df.loc[ok, "position"]).rank(ascending=False, method="min")
    rank = {str(g): int(v) for g, v in zip(df.loc[ok, "gsis_id"], r, strict=True)}
    n = {str(k): int(v) for k, v in df.loc[ok, "position"].value_counts().items()}
    with _lock:
        _ranked.clear()                                                  # one frame held at a time
        _ranked[id(df)] = (df, rank, n)
    return rank, n


def _num(v: Any) -> float | None:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(f) else f


def _ordinal(n: int) -> str:
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _kickoff(v: Any) -> str | None:
    try:
        t = pd.Timestamp(v)
    except (TypeError, ValueError):
        return None
    if pd.isna(t):
        return None
    t = (t.tz_localize("UTC") if t.tzinfo is None else t).tz_convert(ET)
    d: datetime = t.to_pydatetime()
    return f"{d:%a} {d:%-I:%M %p} ET".replace(":00 ", " ")


def card(gsis: str) -> dict | None:
    """{title, description, url} for one player from the held frame, or None (not held, not on it, no projection)."""
    if not isinstance(gsis, str) or not GSIS.fullmatch(gsis):
        return None
    df = held_frame()
    if df is None:
        return None
    m = df[df["gsis_id"] == gsis]
    if m.empty:
        return None
    r = m.iloc[0]
    proj = _num(r.get("proj_points"))
    name, pos, team = r.get("player_name"), r.get("position"), r.get("team")
    if proj is None or not isinstance(name, str) or not name.strip() or pos not in POSITION_WORDS:
        return None
    lo, hi = _num(r.get("p10")), _num(r.get("p90"))
    rng = f", {round(lo)}–{round(hi)}" if lo is not None and hi is not None else ""
    title = f"{name.strip()} ({pos}{', ' + team if isinstance(team, str) and team else ''}): {proj:.1f} projected this week{rng} · {APP_NAME}"
    rank, n = _ranks(df)
    season, week = df.attrs.get("ip5_week", (None, None))
    bits = []
    opp = r.get("opponent")
    if isinstance(opp, str) and opp:
        home = r.get("is_home")
        when = _kickoff(r.get("kickoff_at"))
        side = None if home is None or (isinstance(home, float) and math.isnan(home)) else bool(home)
        bits.append(f"{'vs' if side is True else 'at' if side is False else 'against'} {opp}" + (f", {when}" if when else ""))
    if gsis in rank:
        k = rank[gsis]
        bits.append(f"the {'' if k == 1 else _ordinal(k) + '-'}highest projection of {n.get(pos, 0)} {POSITION_WORDS[pos]} "
                    "this week")
    head = f"Week {week}, {refleague.label(refleague.DEFAULT)}" if week else refleague.label(refleague.DEFAULT)
    desc = f"{head}: " + "; ".join(bits) + "." if bits else f"{head}."
    if lo is not None and hi is not None:
        desc += f" 8 in 10 weeks like this land between {round(lo)} and {round(hi)} points."
    return {"title": title, "description": desc, "url": f"{blog.ORIGIN}/player/{gsis}"}


def shell(index_html, path: str, league_in_query: bool) -> str | None:
    """The page shell for ``/player/<gsis>`` with the player's card (``blog.seo_tags``), or None (the default card)."""
    m = PATH.fullmatch(path or "")
    if m is None:
        return None
    c = card(m.group(1))
    if c is None:
        return None
    pv = {**c, "image": blog.DEFAULT_IMAGE, "type": "profile", "status": 200}
    got = _replace_seo(index_html, blog.seo_tags(pv) + ("\n    " + ROBOTS_META if league_in_query else ""))
    return got


def _replace_seo(index_html, tags: str) -> str | None:
    try:
        text = _index_text(index_html)
    except OSError:
        return None
    i, j = text.find(blog.SEO_START), text.find(blog.SEO_END)
    if i < 0 or j < i:
        return None
    return text[: i + len(blog.SEO_START)] + "\n    " + tags + "\n    " + text[j:]


def _index_text(index_html) -> str:
    """index.html's text through the blog shell's own (mtime-keyed) copy."""
    mtime = index_html.stat().st_mtime
    hit = blog._shells.get(str(index_html))                                                 # noqa: SLF001
    if hit is None or hit[0] != mtime:
        hit = (mtime, index_html.read_text(encoding="utf-8"))
        blog._shells[str(index_html)] = hit                                                 # noqa: SLF001
    return hit[1]


def noindex(text: str) -> str:
    """A shell's HTML with the robots meta tag (a league in the query string), once."""
    if ROBOTS_META in text or "</head>" not in text:
        return text
    return text.replace("</head>", f"  {ROBOTS_META}\n  </head>", 1)


def top(n: int = SITEMAP_TOP) -> list[str]:
    """The sitemap's players: the ``n`` highest projections this week in the default scoring, from the held frame only
    ([] when nothing is held)."""
    df = held_frame()
    if df is None:
        return []
    p = pd.to_numeric(df["proj_points"], errors="coerce")
    d = df.assign(_p=p)[p.notna() & df["gsis_id"].map(lambda g: isinstance(g, str) and bool(GSIS.fullmatch(g)))]
    d = d.sort_values(["_p", "gsis_id"], ascending=[False, True], kind="mergesort").drop_duplicates("gsis_id")
    return [str(g) for g in d["gsis_id"].head(int(n))]

