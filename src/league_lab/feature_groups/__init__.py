"""Feature groups for the harness (plan D1, ``league_lab.experiments``).

One module per group family (``game_context.py``, ``weather.py``, ``team_style.py`` ...), each defining
``GROUPS = {name: spec}``; the harness collects every module's ``GROUPS`` (a name registered twice is an
error). The spec keys are documented in ``league_lab.experiments`` and ``docs/METRICS.md`` § "Feature
experiments". A module per family keeps parallel branches from editing the same lines.
"""
