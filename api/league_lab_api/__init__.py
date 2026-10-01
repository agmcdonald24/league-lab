"""League Lab API. The repository's `src/` (the `league_lab` package: decisions, lineup, scoring, anyleague) is put on
the import path here, before any submodule loads, so `from league_lab import ...` works in every module of the API
(applib did this for the loaded app/lib files only). The Docker image copies `src/league_lab` next to `app/lib`."""

import sys
from pathlib import Path

_SRC = Path(__file__).resolve().parents[2] / "src"
if _SRC.is_dir() and str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))
