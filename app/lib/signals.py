"""Plain-words lines for role alerts and scenario upside (plan R-10 / R-12), shared by Trends, the player
card and Waiver Wire so the three pages say the same thing with the same numbers
(``mart_player_role_alerts``, ``mart_player_scenarios``, ``mart_waiver_upside``). The voice is docs/WORDS.md."""

from __future__ import annotations

import pandas as pd

UPSIDE_MIN_GAIN = 1.0   # waivers.UPSIDE_MIN_GAIN: below it "the projection already counts most of it"
HELD_WORDS = {1: "one game so far", 2: "two games so far", 3: "three games: this is his role now"}


def _s(v) -> str | None:
    return v if isinstance(v, str) and v else None


def _n(v) -> float | None:
    if v is None:
        return None
    try:
        return None if pd.isna(v) else float(v)
    except (TypeError, ValueError):
        return None


def _yes(v) -> bool:
    return bool(v) and not (isinstance(v, float) and pd.isna(v))


def kind_label(r) -> str:
    """The headline word for the alert: what kind of change it is."""
    up = r["direction"] == "up"
    kind = r.get("kind")
    if kind == "absence_beneficiary":
        return "Filling in" if r.get("trigger_status") == "out_injured" else "Taking over the work"
    if kind == "depth_move":
        return "New starter" if up else "Lost his starting job"
    if kind == "new_team":
        return "Bigger role on his new team" if up else "Smaller role on his new team"
    return "Bigger role" if up else "Smaller role"


def cause_phrase(r) -> str:
    """ "Why: Chuba Hubbard out injured." / "Why: no teammate out, no trade: the coaches changed his role." """
    return f"Why: {r['cause_text']}." if _s(r.get("cause_text")) else ""


def held_phrase(r) -> str:
    return HELD_WORDS.get(int(r["games_held"]), f"{int(r['games_held'])} games")


def expiry_phrase(r) -> str:
    """When the alert stops mattering, in words."""
    last = int(r["expires_after_week"]) if _n(r.get("expires_after_week")) is not None else None
    who = _s(r.get("trigger_name"))
    injured = r.get("trigger_status") == "out_injured" or "returns" in (_s(r.get("expiry_rule")) or "")
    if r.get("kind") == "absence_beneficiary" and injured and who:
        if _yes(r.get("trigger_ended")):
            return f"{who} is off the injury report now: the bigger role may end this week."
        return f"It ends when {who} returns" + (f" (check again after week {last})." if last else ".")
    if last is None:
        return ""
    return f"Check again after week {last}: by then his projection has caught up if it holds."


def alert_headline(r, name: str) -> str:
    """ "Filling in: Rico Dowdle — snap share 36% → 67%, carry share 32% → 72% since week 5 (one game so far)" """
    return f"{kind_label(r)}: {name} — {r['change_text']} since week {int(r['since_week'])} ({held_phrase(r)})"


def alert_lines(r) -> str:
    """The card's supporting sentence: the cause and the expiry."""
    return " ".join(x for x in (cause_phrase(r), expiry_phrase(r)) if x)


def scenario_phrase(r, league_name: str | None = None) -> str:
    """The what-if (or, once calibrated, the 'with the alert' line), with the backtest's hit rate, never a bare chance.

    "What if the new role holds: 11.3 in week 4 (projection 7.1, +4.2) in League of Scrubs scoring. Treat it as a what-if,
    not a forecast: tested on 2023–2025, after 285 alerts like this the next three games landed nearer it than the
    projection 46% of the time." """
    base, big, gain = _n(r.get("base_points")), _n(r.get("larger_points")), _n(r.get("points_gain"))
    if base is None or big is None:
        return ""
    wk = f" in week {int(r['week'])}" if _n(r.get("week")) is not None else ""
    scoring = f" in {league_name} scoring" if league_name else ""
    shipped = r.get("presentation") == "with the alert"
    if shipped and _n(r.get("with_alert_points")) is not None:
        head = (f"With the alert he projects {float(r['with_alert_points']):.1f}{wk}{scoring} (projection {base:.1f}; "
                f"{big:.1f} if the new role fully holds).")
    elif gain is not None and gain >= UPSIDE_MIN_GAIN:
        head = f"What if the new role holds: {big:.1f}{wk}{scoring} (projection {base:.1f}, {gain:+.1f})."
    else:
        head = f"The projection already counts most of it: {big:.1f}{wk} if the new role holds, {base:.1f} as he is."
    n, hit = _n(r.get("backtest_n")), _n(r.get("backtest_hit_rate"))
    if n and hit is not None:
        if shipped:
            tail = (f" Tested on 2023–2025: after {int(n)} alerts like this, the next three games landed nearer this line "
                    f"than the projection {100 * hit:.0f}% of the time.")
        else:
            verdict = ("it beat the projection less than half the time, so lean on the projection"
                       if hit < 0.5 else "it beat the projection more often than not")
            tail = (f" Treat it as a what-if, not a forecast: on 2023–2025, after {int(n)} alerts like this, the what-if was "
                    f"closer to what happened next than the projection {100 * hit:.0f}% of the time — {verdict}.")
    else:
        tail = " Treat it as a what-if: not tested on past seasons yet."
    return head + tail


def who_has_him(r, roster_id: int | None) -> str:
    if roster_id is not None and _n(r.get("rostered_by_roster_id")) is not None and int(r["rostered_by_roster_id"]) == int(roster_id):
        return "on your team"
    if _yes(r.get("is_free_agent")):
        return "free agent"
    t = _s(r.get("rostered_by_team"))
    return f"on {t}" if t else ""


# ------------------------------------------------------------------ Waiver Wire: the upside stash region (R-12)
UPSIDE_SQL = """
select u.week, u.horizon_last_week, u.upside_rank, u.add_gsis_id, u.add_name, u.add_position, u.add_team, u.base_value,
       u.scenario_value, u.points_gain, u.with_alert_value, u.presentation, u.since_week, u.games_held, u.confidence, u.kind,
       u.trigger_kind, u.trigger_name, u.cause_text, u.change_text, u.expires_after_week, u.expiry_rule, u.drop_gsis_id,
       u.drop_name, u.drop_position, u.drop_horizon_loss, u.base_weekly_gain, u.base_horizon_gain, u.holds_weekly_gain,
       u.holds_horizon_gain, u.holds_slot, u.open_roster_spots, u.inputs_current
from analytics.mart_waiver_upside u
where u.league_id = %s and u.roster_id = %s and u.week = %s
order by u.upside_rank
"""


def stash_headline(r) -> str:
    """ "Upside stash: Tez Johnson (WR) — snap share 38% → 71% since week 3, Chris Godwin out injured" """
    why = _s(r.get("cause_text"))
    why = f", {why}" if why and r.get("kind") not in ("role_up", "role_down") else ""
    return f"Upside stash: {r['add_name']} ({r['add_position']}) — {r['change_text']} since week {int(r['since_week'])}{why}"


def upside_detail(r) -> list[str]:
    """The card's supporting lines, in the numbers the table shows."""
    wk, last = int(r["week"]), int(r["horizon_last_week"])
    lines = []
    base, big = _n(r["base_value"]), _n(r["scenario_value"])
    if base is not None and big is not None:
        lines.append(f"{held_phrase(r).capitalize()}. He projects {base:.1f} for week {wk} as he is; "
                     f"{big:.1f} if the bigger role holds (a what-if, not a forecast).")
    hw, hh = _n(r["holds_weekly_gain"]) or 0.0, _n(r["holds_horizon_gain"]) or 0.0
    if hh > 0.05:
        where = f" at {r['holds_slot']}" if _s(r["holds_slot"]) and hw > 0.05 else ""
        lines.append(f"As he is he would not start for you; if it holds, claiming him adds {hw:+.1f} to your week-{wk} "
                     f"lineup{where} and {hh:+.1f} over weeks {wk}–{last}.")
    else:
        lines.append(f"Even if it holds he would not start for you in weeks {wk}–{last}: a stash, not a starter yet.")
    if _s(r["drop_name"]):
        loss = _n(r["drop_horizon_loss"]) or 0.0
        lines.append(f"Drop {r['drop_name']} ({r['drop_position']}): "
                     + (f"costs your lineup {loss:.1f} over weeks {wk}–{last}." if loss > 0.05 else f"he would not start for you in weeks {wk}–{last}."))
    else:
        lines.append("You have an open roster spot, so nobody has to go.")
    exp = expiry_phrase(r)
    if exp:
        lines.append(exp)
    return lines


def upside_cards(league_id: str, roster_id: int, week: int) -> None:
    """Waiver Wire's third card region: the best upside stash as a card, the rest in an expander."""
    import streamlit as st

    from lib.db import missing_relations, query
    from lib.table import show
    from lib.ui import player_link

    if missing_relations(("mart_waiver_upside",)):
        st.caption("Upside stashes (a player whose role is growing before his points do) arrive with the nightly update.")
        return
    up = query(UPSIDE_SQL, (league_id, roster_id, week))
    if up.empty:
        st.caption(f"No upside stash for week {week}: no free agent's role grew in his last one to three games without "
                   "already making the lists above (see Trends for every role change).")
        return
    r = up.iloc[0]
    with st.container(border=True):
        st.caption("Upside stash: his role is growing before his points do")
        head = stash_headline(r).replace(str(r["add_name"]), player_link(r["add_gsis_id"], r["add_name"]), 1)
        st.markdown(f"**{head}**")
        st.markdown("  \n".join(upside_detail(r)))
    if len(up) > 1:
        with st.expander(f"All {len(up)} upside stashes"):
            tab = up.assign(upside_stash=up["add_name"] + " " + up["add_position"], upside_drop=up["drop_name"],
                            role_change=up["change_text"], upside_if_holds=up["scenario_value"], upside_gain=up["holds_horizon_gain"],
                            role_cause=up["cause_text"])
            show(tab, ["upside_stash", "role_change", "upside_if_holds", "upside_gain", "upside_drop", "role_cause"],
                 phone_cols=["upside_stash", "role_change", "upside_if_holds", "upside_gain", "upside_drop"],
                 links={"upside_stash": ("add_gsis_id", "add_name"), "upside_drop": ("drop_gsis_id", "drop_name")})
            st.caption("Each stash with the drop your lineup misses least. **If it holds** is his projection this week with his "
                       "bigger role (a what-if); **Lineup gain if it holds** adds up the next four weeks.")
