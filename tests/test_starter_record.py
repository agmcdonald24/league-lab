"""IW-1 round 3: the starter record (league_lab.starter_record): the words of About's line, the freeze at kickoff and
the grade, as statements (the plumbing on a database is shown in docs/STATUS.md § "Wave I-W" (IW-1) on a pretend week)."""

from __future__ import annotations

from league_lab import starter_record as R


def test_about_says_nothing_while_no_game_is_graded():
    assert R.sentence(0, 0) is None
    assert R.sentence(2, 3) == "Our projected starter was the game's quarterback in 2 of 3 games since week 5."


def test_a_row_is_rewritten_only_before_its_kickoff_and_never_once_graded():
    w = " ".join(R.WRITE_SQL.split())
    assert "on conflict (season, week, team) do update" in w
    assert "where r.kickoff_at > %(now)s and r.truth_qb_id is null" in w
    assert "t.kickoff_at > %(now)s" in w and "t.listed_qb_id is not null" in w


def test_the_grade_reads_the_dropback_leader_and_grades_every_pick():
    g = " ".join(R.GRADE_SQL.split())
    assert "order by p.season, p.week, p.team, p.dropbacks desc, p.gsis_id" in g     # mart_starter_check's leader
    for col in ("listed_right", "s4_right", "s7_right", "projected_right"):
        assert f"{col} = (" in g
    assert "r.truth_qb_id is null and r.kickoff_at <= %(now)s" in g


def test_migrate_creates_the_table():
    import inspect

    from league_lab import db

    assert "starter_record.DDL" in inspect.getsource(db.migrate)
