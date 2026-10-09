"""IU-3 (Wave I-U): small things that made screens disagree or read oddly. Hand-built blocks and caveats; no database,
nothing cached between tests (each builds its own inputs)."""

from league_lab import availability_gate as AG
from league_lab import league_status as LS


def _block(code, note=None, as_of="2026-10-08T15:00:00Z", source="ESPN"):
    return AG.classify(AG.entry(code, source, as_of=as_of, note=note))


def test_start_sit_softens_for_a_hand_set_starter_and_withholds_for_an_unclear_one(monkeypatch):
    from league_lab_api import provenance as PV
    from league_lab_api import rankings_api as RA
    from league_lab_api import starters as ST

    def caveats_for(players, season, week):
        return [{"kind": "starter_set_by_hand", "effect": PV.SOFTEN, "team": "SEA", "players": ["Sam Darnold"],
                 "listed": "Drew Lock", "set": "Sam Darnold", "words": "… read the verdict as a lean …"},
                {"kind": "starter_unclear", "effect": PV.WITHHOLD, "team": "TB", "players": ["Baker Mayfield"],
                 "listed": "Jalon Daniels", "other": "Baker Mayfield", "words": "No verdict while …"}]
    monkeypatch.setattr(PV, "caveats_for", caveats_for)
    monkeypatch.setattr(ST, "team_name", lambda t: {"TB": "Tampa Bay", "SEA": "Seattle"}.get(t, t))
    cvs = RA.start_caveats([{"gsis_id": "x"}], 2026, 5)
    assert cvs[0]["words"] == ("Read it as a lean: Seattle's starter was set by hand (Sam Darnold, not the listed Drew "
                               "Lock), and this call assumes Darnold starts.")
    assert cvs[1]["words"].startswith("Tampa Bay's starter is unclear: Jalon Daniels is listed")
    assert all("verdict" not in c["words"] for c in cvs) and cvs[0]["verdict_words"] == "… read the verdict as a lean …"
    assert PV.effect(cvs) == PV.WITHHOLD
    monkeypatch.setattr(PV, "caveats_for", lambda *a: (_ for _ in ()).throw(RuntimeError("no flags")))
    assert RA.start_caveats([{"gsis_id": "x"}], 2026, 5) == []            # a label never costs an answer


def test_the_card_says_a_questionable_players_rate_by_position():
    from league_lab_api import player as P
    q = _block("QUESTIONABLE", "hamstring")
    n_wr, n_qb = LS.note(q, position="WR"), LS.note(q, position="QB")
    assert n_wr["rate_words"] == AG.short_words(q, "WR") and n_wr["rate_words"].startswith("Questionable: about ")
    assert n_qb["rate_words"] == AG.short_words(q, "QB")
    assert P._status_words(n_wr) == f" {n_wr['rate_words']}."
    ir = LS.note(_block("IR", "knee - acl", source="Sleeper"), position="RB")
    assert ir["rate_words"] is None and P._status_words(ir) == f" {ir['words']}"     # he sits: the reason, not a rate
    assert LS.note(None, position="WR") is None


def test_trends_ask_league_gate_not_the_older_overlay():
    import inspect

    from league_lab_api import research as R
    src = inspect.getsource(R.trends)
    assert "NOT_IN_TRENDS)" not in src and "LG.sits" in src
