# All targets run through uv; `uv sync` happens implicitly via `uv run`.
# `make verify` reproduces the full merge gate end to end.

.PHONY: help install gen-demo ingest qc calibrate aggregate export serve demo rebuild \
        fmt fmt-check lint typecheck test a11y i18n hygiene version-check reading-level \
        verify check clean

help:  ## List available targets
	@grep -E '^[a-zA-Z_-]+:.*?## ' $(MAKEFILE_LIST) \
		| awk 'BEGIN{FS=":.*?## "}{printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'

install:  ## Sync the environment (runtime + dev) from pyproject/uv.lock
	uv sync

gen-demo:  ## Regenerate the committed demo dataset + network.yaml (deterministic)
	uv run python scripts/gen_demo_data.py

ingest:  ## Ingest the recorded demo payloads into ./store
	uv run swelter ingest data/demo/observations.jsonl --store store

qc:  ## Report node health and data gaps for ./store
	uv run swelter qc --store store

calibrate:  ## Fit corrections from co-location data and apply them to ./store
	uv run swelter calibrate --store store

aggregate:  ## Build the gridded heat-island / AQI surface
	uv run swelter aggregate --store store

export:  ## Export ./store observations as CSV to stdout
	uv run swelter export --store store --format csv

serve:  ## Serve the dashboard, API, and exports at http://127.0.0.1:8000
	uv run swelter serve --store store

demo:  ## Replay the recorded week through the pipeline and serve the dashboard
	uv run swelter demo --serve

rebuild:  ## Rebuild calibrated values + surface from immutable raw observations
	uv run swelter rebuild --store store/demo

fmt:  ## Format the code
	uv run ruff format src tests scripts

fmt-check:  ## Check formatting without writing
	uv run ruff format --check src tests scripts

lint:  ## Lint (ruff)
	uv run ruff check src tests scripts

typecheck:  ## Type-check (mypy, strict)
	uv run mypy

test:  ## Run the test suite with branch coverage, gated at the floor
	uv run pytest --cov=swelter --cov-branch --cov-report=term-missing --cov-fail-under=90

a11y:  ## Structural accessibility gate on the dashboard (WCAG 2.2 AA subset)
	uv run python scripts/a11y_check.py

i18n:  ## Mechanical i18n gates: UTF-8 (G1), BCP-47 tags (G3/G4), EN/ES parity (G6), CLDR pin (G12)
	uv run python scripts/i18n_encoding_check.py
	uv run python scripts/i18n_bcp47_check.py
	uv run python scripts/i18n_parity.py
	uv run python scripts/i18n_cldr_pin_check.py

hygiene:  ## No bare TODO/FIXME/HACK; every noqa/type:ignore is coded (CQ-34/CQ-35)
	uv run python scripts/hygiene_check.py

version-check:  ## Tag == pyproject.toml == CHANGELOG parity, once a v* tag exists (REL-02/03)
	uv run python scripts/version_check.py

reading-level:  ## Advisory (not merge-blocking yet): Flesch-Kincaid grade over en.json (A11Y-23)
	uv run python scripts/reading_level_check.py

verify: fmt-check lint typecheck a11y i18n hygiene version-check test  ## The full merge gate, end to end
	@echo "swelter: all gates green"

check: verify  ## Alias for verify

clean:  ## Remove caches and the local runtime store
	rm -rf .ruff_cache .mypy_cache .pytest_cache store
