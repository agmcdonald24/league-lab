"""PO glue (Wave I-R): the starter-caveat rule applied to the one trade decision (provenance.rule_trade) and the trade
verdict's out-indefinitely hook reading IR-1's definition. Hand-built answers; no database."""

from league_lab_api import provenance as P


def _ans(caveats):
    return {"verdict": "Helps your lineup.", "caveats": caveats,
            "decision": {"verdict": "Helps your lineup.",
                         "recommendation": {"credible": True, "key": "propose", "label": "Worth proposing", "words": "Both gain."}}}


def test_no_caveat_leaves_the_decision_alone():
    a = _ans([])
    assert P.rule_trade(a) is a
    assert P.rule_trade({"x": 1}) == {"x": 1} and P.rule_trade(None) is None


def test_an_unclear_starter_withholds_the_verdict_and_the_recommendation():
    cv = {"kind": "starter_unclear", "effect": P.WITHHOLD, "team": "TB", "players": ["Baker Mayfield"],
          "words": "No verdict while Tampa Bay's starter is unclear: Jalon Daniels is listed, the depth chart puts Baker Mayfield first."}
    out = P.rule_trade(_ans([cv]))
    d = out["decision"]
    assert d["verdict"] == cv["words"] and out["verdict"] == cv["words"]          # one verdict, in both places
    assert d["verdict_unqualified"] == "Helps your lineup."
    assert d["recommendation"]["credible"] is False and d["recommendation"]["label"] == "No recommendation"
    assert d["recommendation"]["words_unqualified"] == "Both gain."
    assert d["caveat"] == {"effect": P.WITHHOLD, "words": cv["words"]}


def test_a_hand_set_starter_softens_it_to_a_lean():
    cv = {"kind": "starter_corrected", "effect": P.SOFTEN, "team": "SEA", "players": ["Sam Darnold"],
          "words": "Read this verdict as a lean that assumes Darnold starts."}
    out = P.rule_trade(_ans([cv]))
    d = out["decision"]
    assert d["verdict"] == "Helps your lineup."                                   # the verdict stands
    assert d["recommendation"]["label"] == "Worth proposing (a lean)"
    assert d["recommendation"]["words"].endswith(cv["words"]) and d["recommendation"]["credible"] is True
    assert d["caveat"]["effect"] == P.SOFTEN


def test_a_broken_answer_is_returned_as_it_is():
    a = {"decision": {"verdict": "x", "recommendation": None}, "caveats": [{"effect": P.WITHHOLD}]}   # a caveat with no words
    assert P.rule_trade(a)["decision"]["verdict"] in ("x", "")                    # never raises


# ---- PO hotfix 2026-10-08: /api/ready through the hosted pooler
def test_the_readiness_probe_sends_no_startup_options(monkeypatch):
    """The hosted database sits behind a pooler that refuses startup options (`options=-c statement_timeout=…`): with
    them every probe on the live site answered 503 "does not answer" while the app's own pool served every screen. The
    timeout is set inside the probe's transaction instead."""
    from league_lab_api import ready

    seen: dict = {"kwargs": None, "sql": []}

    class Conn:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql, *a, **k):
            seen["sql"].append(str(sql))
            raise ready.psycopg.errors.UndefinedTable("stop here")

    def connect(*a, **k):
        seen["kwargs"] = k
        return Conn()

    monkeypatch.setattr(ready.psycopg, "connect", connect)
    ok, ans = ready.check("postgresql://nobody@localhost:1/none")
    assert ok is False and ans["code"] == "query"
    assert "options" not in seen["kwargs"]
    assert seen["sql"] and seen["sql"][0].startswith("set local statement_timeout")
