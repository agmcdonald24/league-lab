"""Plan D3: the weather feature groups for the feature-group harness (``league-lab experiment``).

Table: ``intermediate.int_player_week_weather`` (dbt/models/intermediate/features/), the contract grain
(gsis_id, season, week). Values are the player's game's weather (Open-Meteo forecast for the live board;
for past games the Open-Meteo archive, else the schedules' observed temp / wind): no column is built from
earlier games of the season, so there is no ``in_season`` list. ``wx_source`` is bookkeeping, not an input.

Until the first real Open-Meteo run backfills ``raw.nfl_weather``, past games carry only the schedules'
temp and wind: ``wx_gust_mph``, ``wx_precip_in`` and ``wx_snow`` are 0 in a dome and NULL outdoors (so
they act as a second dome flag), and precipitation cannot be judged yet.
"""

_TABLE = "intermediate.int_player_week_weather"

GROUPS = {
    "weather": {
        "table": _TABLE,
        "columns": ["wx_dome", "wx_wind_mph", "wx_gust_mph", "wx_precip_in", "wx_temp_f", "wx_cold", "wx_windy", "wx_snow"],
        "label": "Game-day weather: wind, gusts, rain or snow, temperature, dome",
        "note": "Open-Meteo at the stadium, kickoff hour and the two after (forecast for the board, observed for past games).",
    },
    "wind": {
        "table": _TABLE,
        "columns": ["wx_wind_mph", "wx_gust_mph", "wx_windy"],
        "label": "Wind at kickoff",
        "note": "Mean wind and max gust (mph) over the game's first three hours; 0 in a dome.",
    },
    "temp": {
        "table": _TABLE,
        "columns": ["wx_temp_f", "wx_cold"],
        "label": "Temperature at kickoff",
        "note": "Mean temperature (°F) over the game's first three hours and a below-freezing flag; 0 in a dome.",
    },
    "dome": {
        "table": _TABLE,
        "columns": ["wx_dome"],
        "label": "Dome or closed roof",
        "note": "Fixed dome, or a retractable roof that is closed (undecided counts as closed).",
    },
}
