# All targets run through uv; `uv sync` happens implicitly via `uv run`.
# `make verify` reproduces the full merge gate end to end.

.PHONY: help install gen-demo ingest qc calibrate aggregate export serve demo rebuild snapshot \
        fmt fmt-check lint typecheck test a11y i18n seo hygiene version-check reading-level \
        docs-figures docs-contract adr-immutability standards-pin standards-pin-upstream \
        acceptance-map dora-evidence conformance log-safety workflow-policy \
        web-install web-unit web-browser web-test verify-web firmware-test infra-synth \
        security-pip security-osv security-node security-secrets security-semgrep \
        security-workflows verify-security package sbom sbom-validate verify-package \
        mutation-tool-smoke mutation-run mutation-report mutation \
        mutation-baseline-candidate mutation-baseline-check release-readiness \
        verify-core verify check clean

PIP_AUDIT_VERSION := 2.10.1
SEMGREP_VERSION := 1.169.0
ZIZMOR_VERSION := 1.26.1
GITLEAKS_VERSION := 8.30.1
OSV_SCANNER_VERSION := 2.3.8
CDK_CLI_VERSION := 2.1132.0
MUTMUT_VERSION := 3.6.0
MUTATION_SCORE_FLOOR ?= 80
MUTATION_EVIDENCE_DATE ?=
OSV_SCANNER ?= osv-scanner
SECURITY_REPORT_DIR ?= dist/security
PLAYWRIGHT_INSTALL_ARGS ?= chromium firefox webkit

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

snapshot:  ## Freeze a citable, versioned data release (MANIFEST + dataset CITATION.cff/.txt)
	uv run swelter snapshot --store store --out dist/snapshot

fmt:  ## Format the code
	uv run ruff format src tests scripts infra/cdk

fmt-check:  ## Check formatting without writing
	uv run ruff format --check src tests scripts infra/cdk

lint:  ## Lint (ruff)
	uv run ruff check src tests scripts infra/cdk

typecheck:  ## Type-check (mypy, strict)
	uv run mypy

test:  ## Run the test suite with branch coverage, gated at the floor
	uv run pytest --cov=swelter --cov-branch --cov-report=term-missing --cov-fail-under=90

a11y:  ## Structural accessibility gate on the dashboard (WCAG 2.2 AA subset)
	uv run python scripts/a11y_check.py

i18n:  ## Mechanical i18n gates: gettext/MF2 catalogs, parity, tags, UTF-8, CLDR freshness
	uv run python scripts/i18n_encoding_check.py
	uv run python scripts/i18n_bcp47_check.py
	uv run python scripts/gettext_catalog_check.py
	uv run python scripts/i18n_parity.py
	uv run python scripts/i18n_cldr_pin_check.py

seo:  ## Validate Pages metadata inputs and the GitHub project-site crawl policy
	uv run python scripts/pages_seo.py check --template web/index.html

hygiene:  ## No bare TODO/FIXME/HACK; every noqa/type:ignore is coded (CQ-34/CQ-35)
	uv run python scripts/hygiene_check.py

version-check:  ## Tag == pyproject.toml == CHANGELOG parity, once a v* tag exists (REL-02/03)
	uv run python scripts/version_check.py

reading-level:  ## Block prose above the Flesch-Kincaid grade ceiling (A11Y-23)
	uv run python scripts/reading_level_check.py

docs-figures:  ## Re-prove countable claims in docs against their sources of truth (report-only where prose is agent-do-not-modify)
	uv run python scripts/docs_figures_check.py

docs-contract:  ## Verify documentation claims against executable repository state
	uv run python scripts/docs_contract_check.py

adr-immutability:  ## Prevent rewrites or deletion of ADRs Accepted at the comparison base
	uv run python scripts/adr_immutability_check.py

standards-pin:  ## Byte-verify the vendored portfolio standards release
	uv run python scripts/standards_pin_check.py

standards-pin-upstream:  ## Authenticate the standards pin against the canonical GitHub release
	uv run python scripts/standards_pin_check.py --upstream

acceptance-map:  ## Verify feature rows, test anchors, ISO vocabulary, and roadmap coverage
	uv run python scripts/acceptance_map_check.py

dora-evidence:  ## Verify retained DORA inputs, digests, snapshot, and generated ledger
	uv run python scripts/dora_evidence.py check

conformance:  ## Validate the README standards ledger (and linked issue state in CI)
	uv run python scripts/conformance_check.py

log-safety:  ## Reject production logging that can expose PII or credentials
	uv run python scripts/log_safety_check.py

workflow-policy:  ## Enforce immutable Actions, exact version comments, and fail-closed gates
	uv run python scripts/workflow_policy_check.py

web-install:  ## Install the exact dashboard test toolchain
	npm --prefix web ci

web-unit: web-install  ## Run dashboard unit, schema, i18n, and conformance tests
	npm --prefix web run test:unit

web-browser: web-install  ## Run Playwright, pa11y, and Lighthouse browser gates
	npm --prefix web exec -- playwright install $(PLAYWRIGHT_INSTALL_ARGS)
	npm --prefix web run test:a11y

web-test: web-unit  ## Backward-compatible alias for dashboard unit tests

verify-web: web-install  ## Run the complete dashboard gate through its canonical script
	npm --prefix web exec -- playwright install $(PLAYWRIGHT_INSTALL_ARGS)
	npm --prefix web run verify

firmware-test:  ## Compile and test the hardware-free MicroPython firmware core
	uv run python -m compileall -q firmware/src
	uv run pytest firmware/tests -q

infra-synth:  ## Synthesize the optional AWS stack with locked libraries and exact CDK CLI
	uv sync --locked --group infra
	cd infra/cdk && npx --yes aws-cdk@$(CDK_CLI_VERSION) synth --output cdk.out

security-pip:  ## Audit the locked Python dependency graph with no vulnerability waiver
	REQ="$$(mktemp)"; \
	uv export --frozen --no-emit-project --all-groups --no-hashes \
	  --format requirements-txt --output-file "$$REQ" \
	  && uv run --with pip-audit==$(PIP_AUDIT_VERSION) pip-audit --requirement "$$REQ"; \
	STATUS=$$?; rm -f "$$REQ"; exit $$STATUS

security-osv:  ## Scan all supported lockfiles against OSV
	test "$$($(OSV_SCANNER) --version | sed -n '1s/^osv-scanner version: //p')" = "$(OSV_SCANNER_VERSION)"
	$(OSV_SCANNER) scan source -r .

security-node:  ## Block HIGH/CRITICAL npm dependency findings
	npm --prefix web audit --audit-level=high

security-secrets:  ## Scan complete Git history with the pinned gitleaks CLI
	test "$$(gitleaks version)" = "$(GITLEAKS_VERSION)"
	gitleaks git --redact --exit-code 1 --no-banner .

security-semgrep:  ## Run blocking Semgrep SAST and retain SARIF for Code Scanning
	mkdir -p $(SECURITY_REPORT_DIR)
	uv run --with semgrep==$(SEMGREP_VERSION) semgrep scan --error --config=p/default --config=p/python \
		--severity=ERROR --severity=WARNING \
		--exclude-rule=python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query \
		--exclude-rule=python.lang.security.audit.formatted-sql-query.formatted-sql-query \
		--exclude-rule=python.lang.security.audit.httpsconnection-detected.httpsconnection-detected \
		--exclude-rule=python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected \
		--exclude-rule=python.lang.compatibility.python37.python37-compatibility-importlib2 \
		--sarif --output=$(SECURITY_REPORT_DIR)/semgrep.sarif
# Excluded rules are categorical false positives here: no SQLAlchemy exists in the repo; the sqlite3
# queries use fixed columns with ?-bound values; HTTPS clients target hardcoded hosts; the floor is
# Python 3.12. Granular re-narrowing is tracked in #107.

security-workflows: workflow-policy  ## Run workflow SAST at HIGH severity
	uvx zizmor@$(ZIZMOR_VERSION) --min-severity=high .github/workflows

verify-security: security-secrets security-pip security-osv security-node security-semgrep security-workflows  ## Run every local security gate

package:  ## Build the wheel and source distribution
	uv build

sbom: package  ## Generate one artifact-bound CycloneDX 1.7 BOM per package
	@for artifact in dist/*.whl dist/*.tar.gz; do \
		uv run python scripts/release_artifacts.py generate-sbom \
			--artifact "$$artifact" --output "$$artifact.cdx.json"; \
	done

sbom-validate: sbom  ## Apply the local CycloneDX 1.7 policy validator
	uv run python scripts/release_artifacts.py validate-sbom dist/*.cdx.json

verify-package: sbom-validate  ## Build and validate release-package evidence

mutation-tool-smoke:  ## Assert that the exact locked mutation engine is active
	test "$$(uv run --group mutation mutmut --version)" = "mutmut, version $(MUTMUT_VERSION)"

mutation-run: mutation-tool-smoke  ## Mutate the selected core safety modules
	uv run --group mutation mutmut run \
		"swelter.calibrate*" "swelter.models*" "swelter.qc*"

mutation-report:  ## Enforce killed/all score and fail on incomplete mutation states
	uv run python scripts/mutation_report.py report \
		--mutants mutants \
		--json dist/mutation/report.json \
		--markdown dist/mutation/report.md \
		--minimum-score $(MUTATION_SCORE_FLOOR)

mutation: mutation-run mutation-report  ## Run the complete core mutation gate

mutation-baseline-candidate: mutation-report  ## Render a candidate dated baseline for review
	test -n "$(MUTATION_EVIDENCE_DATE)"
	uv run python scripts/mutation_report.py baseline \
		--report dist/mutation/report.json \
		--evidence-date $(MUTATION_EVIDENCE_DATE) \
		--json dist/mutation/mutation-baseline.json \
		--markdown dist/mutation/mutation-baseline.md \
		--minimum-score $(MUTATION_SCORE_FLOOR)

mutation-baseline-check:  ## Fail when committed mutation evidence is stale or non-passing
	uv run python scripts/mutation_report.py verify-baseline \
		--baseline docs/audits/mutation-baseline.json

release-readiness: mutation-baseline-check  ## Verify release-only committed evidence is current
	uv run python scripts/release_artifacts.py validate-publishing-gap \
		docs/audits/release-publishing-gap.json
	uv run python scripts/release_review_check.py validate \
		--manifest docs/audits/release-review-attestations.json \
		--version "$$(uv run python -c 'import swelter; print(swelter.__version__)')" \
		--require-complete

verify-core: fmt-check lint typecheck a11y i18n seo hygiene version-check reading-level docs-figures docs-contract adr-immutability standards-pin acceptance-map dora-evidence conformance log-safety workflow-policy test  ## Python/docs merge gate

verify: verify-core verify-web firmware-test infra-synth verify-security verify-package  ## Every automatic local gate, end to end
	@echo "swelter: all gates green"

check: verify  ## Alias for verify

clean:  ## Remove caches and the local runtime store
	rm -rf .ruff_cache .mypy_cache .pytest_cache store
