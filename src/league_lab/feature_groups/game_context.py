"""Plan D2: game context (``intermediate.int_player_week_game_context``, all from the published schedule).

``game_context`` is the whole table; ``rest``, ``time`` and ``venue`` split it so the harness table shows
which part helps (``league-lab experiment game_context rest time venue`` runs the four in one session)."""

TABLE = "intermediate.int_player_week_game_context"

REST = ["gc_rest_days", "gc_short_week", "gc_off_bye", "gc_opp_rest_days", "gc_rest_edge"]
TIME = ["gc_weekday", "gc_kickoff_hour_et", "gc_primetime", "gc_early_window", "gc_travel_tz", "gc_west_coast_early"]
VENUE = ["gc_roof", "gc_surface_turf", "gc_div_game", "gc_neutral_site"]

GROUPS = {
    "game_context": {
        "table": TABLE, "columns": [*TIME, *REST, *VENUE],
        "label": "Game context: all of it",
        "note": "D2: weekday, kickoff hour, primetime, 1 pm window, rest days / short week / off a bye / rest edge, "
                "time zones crossed, west-coast team at 1 pm ET, dome, turf, division game, neutral site",
    },
    "rest": {
        "table": TABLE, "columns": REST,
        "label": "Rest days",
        "note": "D2 sub-group: days since the last game (his team, the opponent, the edge), short week, off a bye",
    },
    "time": {
        "table": TABLE, "columns": TIME,
        "label": "Kickoff time, travel",
        "note": "D2 sub-group: weekday, kickoff hour ET, primetime, 1 pm window, time zones crossed, west-coast team at 1 pm ET",
    },
    "venue": {
        "table": TABLE, "columns": VENUE,
        "label": "Stadium, division",
        "note": "D2 sub-group: fixed dome (retractable unknown), artificial turf, division game, neutral site",
    },
}
