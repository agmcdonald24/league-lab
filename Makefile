# League Lab — common entrypoints. Every target runs inside the uv-managed venv.
.DEFAULT_GOAL := help
SHELL := /bin/bash

help: ## list targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

setup: ## one-shot local setup (macOS): postgres, roles, venv, pilot data, dbt build
	./scripts/bootstrap.sh

sync: ## install/refresh python deps from uv.lock
	uv sync --locked

migrate: ## create schemas + ops tables (idempotent)
	uv run league-lab db migrate

check: ## verify both database roles
	uv run league-lab db check

ingest-sleeper: ## league chain, matchups, transactions, drafts, players
	uv run league-lab ingest sleeper

ingest-nfl: ## nflverse for SEASONS (default: all from LEAGUE_LAB_SEASONS_START)
	uv run league-lab ingest nfl $(if $(SEASONS),--seasons $(SEASONS),)

pilot: ## Sleeper + previous/current NFL seasons only
	uv run league-lab ingest sleeper
	uv run league-lab ingest nfl --seasons $$(uv run python -c 'from league_lab.ingest.nflverse import current_nfl_season as c; print(f"{c()-1},{c()}")')

fit-rankings: ## refit the baseline projection weights on TRAIN seasons (default 2019-2022), then `make build`
	uv run league-lab fit-rankings --train $(or $(TRAIN),2019-2022)

backtest: ## score the rankings on held-out SEASONS (default 2023-2025); writes reports/backtests + ops.backtest_results
	uv run league-lab backtest --seasons $(or $(SEASONS),2023-2025)

backtest-v2: ## walk-forward backtest of projection v2 on SEASONS (default 2021-2025); writes reports/backtests + ops.projection_backtest
	uv run league-lab backtest-v2 --seasons $(or $(SEASONS),2021-2025)

project: ## fit projection v2 on completed seasons, write this season's projections (ops.projections), publish the mart
	uv run league-lab project
	uv run league-lab dbt build --select mart_player_week_projections+ mart_projection_backtest+

backfill: ## full nflverse history (2016+)
	uv run league-lab ingest nfl

dbt-deps: ## install dbt packages
	uv run league-lab dbt deps

build: ## dbt seed + run + test (runs migrate first so ops tables from newer code exist)
	uv run league-lab db migrate
	uv run league-lab dbt build

test: ## dbt tests only
	uv run league-lab dbt test

docs: ## dbt docs (generate + serve on 8080)
	uv run league-lab dbt docs generate
	uv run league-lab dbt docs serve --port 8080

sync-hosted: ## publish the marts to the hosted database (needs LEAGUE_LAB_HOSTED_ADMIN_URL + LEAGUE_LAB_HOSTED_APP_PASSWORD in .env)
	./scripts/sync_to_hosted.sh

refresh: ## the nightly pipeline + a local backup (= scripts/refresh.sh, what launchd runs; hosted sync when configured)
	./scripts/refresh.sh

nightly: ## the nightly pipeline exactly as GitHub Actions runs it (scripts/nightly.sh; NIGHTLY_SLEEPER_OFFLINE=1 skips live Sleeper)
	./scripts/nightly.sh

status: ## load manifest summary
	uv run league-lab status

app: ## run the Streamlit explorer on 127.0.0.1:8501
	uv run streamlit run app/Home.py --server.address 127.0.0.1 --server.port 8501

backup: ## pg_dump the analytics database into backups/
	./scripts/backup.sh

pytest: ## python unit tests (no database required)
	uv run pytest -q

lint: ## ruff
	uv run ruff check src app tests

.PHONY: help setup sync migrate check ingest-sleeper ingest-nfl fit-rankings backtest backtest-v2 project sync-hosted pilot backfill dbt-deps build test docs refresh nightly status app backup pytest lint

teams: ## roster ids and team names for the current league
	uv run league-lab teams

weekly-pack: ## facts pack for the newsletter: make weekly-pack WEEK=3 TEAM=2
	uv run league-lab weekly-pack $(if $(WEEK),--week $(WEEK),) $(if $(TEAM),--team $(TEAM),)

.PHONY: teams weekly-pack
