.PHONY: bootstrap bootstrap-full data-download data-audit reference environment environment-build environment-replay grade-reference variants runtime-image runtime-preflight runtime-smoke smoke-plan analyze report pre-release-audit verify-v0 v05-controls v05-reference v05-demo v05-report v05-freeze v05-plan v05-analyze v05-test v06-controls v06-provider-plan v06-compatibility-plan v06-cost-plan v06-freeze-preview v06-pilot-plan v06-probe-analyze v06-test v07-controls v07-test doctor demo status audit-check test lint check

bootstrap:
	./scripts/bootstrap_local.sh

bootstrap-full:
	./scripts/bootstrap_full.sh

data-download:
	PYTHONPATH=src ./.venv/bin/python scripts/download_data.py

data-audit:
	PYTHONPATH=src ./.venv/bin/python scripts/build_data_audit.py

reference:
	PYTHONPATH=src ./.venv/bin/python scripts/run_reference_episode.py

environment: environment-build environment-replay

environment-build:
	PYTHONPATH=src ./.venv/bin/python scripts/build_environment.py

environment-replay:
	PYTHONPATH=src ./.venv/bin/python scripts/replay_reference_environment.py

grade-reference:
	PYTHONPATH=src ./.venv/bin/python scripts/grade_reference_separation.py

variants:
	PYTHONPATH=src ./.venv/bin/python scripts/build_variant_controls.py

runtime-image:
	/usr/bin/env PATH=/Applications/Docker.app/Contents/Resources/bin:/usr/local/bin:/usr/bin:/bin /Applications/Docker.app/Contents/Resources/bin/docker build --tag uc-bench-agent:0.1 --file docker/agent.Dockerfile .

runtime-preflight:
	PYTHONPATH=src ./.venv/bin/python scripts/run_docker_preflight.py

runtime-smoke:
	PYTHONPATH=src ./.venv/bin/python scripts/run_infrastructure_smoke.py

smoke-plan:
	PYTHONPATH=src ./.venv/bin/python scripts/run_smoke_pilot.py

analyze:
	PYTHONPATH=src ./.venv/bin/python scripts/analyze_evaluation.py

report: analyze
	PYTHONPATH=src ./.venv/bin/python scripts/build_report.py

pre-release-audit: analyze
	PYTHONPATH=src ./.venv/bin/python scripts/run_pre_release_audit.py

verify-v0: check reference environment grade-reference variants runtime-smoke report pre-release-audit

v05-controls:
	PYTHONPATH=src ./.venv/bin/python scripts/build_v05_controls.py

v05-reference:
	PYTHONPATH=src ./.venv/bin/python scripts/replay_v05_reference.py

v05-demo:
	PYTHONPATH=src ./.venv/bin/python scripts/build_v05_demo.py --replace

v05-report:
	PYTHONPATH=src ./.venv/bin/python scripts/build_v05_precalibration_report.py

v05-freeze:
	PYTHONPATH=src ./.venv/bin/python scripts/freeze_v05.py

v05-plan:
	PYTHONPATH=src ./.venv/bin/python scripts/run_v05_calibration.py

v05-analyze:
	PYTHONPATH=src ./.venv/bin/python scripts/analyze_v05.py

v05-test:
	PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_hard_suite_v05.py tests/test_v05_analysis.py

v06-controls:
	PYTHONPATH=src ./.venv/bin/python scripts/build_v06_controls.py

v06-provider-plan:
	PYTHONPATH=src ./.venv/bin/python scripts/build_v06_provider_plan.py

v06-compatibility-plan:
	PYTHONPATH=src ./.venv/bin/python scripts/run_v06_compatibility.py

v06-cost-plan:
	PYTHONPATH=src ./.venv/bin/python scripts/build_v06_cost_plan.py

v06-freeze-preview:
	PYTHONPATH=src ./.venv/bin/python scripts/freeze_v06.py

v06-pilot-plan:
	PYTHONPATH=src ./.venv/bin/python scripts/run_v06_pilot.py --strategy sentinel

v06-probe-analyze:
	PYTHONPATH=src ./.venv/bin/python scripts/analyze_v06_probe.py

v06-test:
	PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_hard_suite_v06.py tests/test_v06_compatibility.py tests/test_v06_provider.py tests/test_v06_execution.py tests/test_v06_cost_plan.py

v07-controls:
	PYTHONPATH=src ./.venv/bin/python scripts/build_v07_controls.py

v07-test:
	PYTHONPATH=src ./.venv/bin/python -m pytest tests/test_hard_suite_v07.py

doctor:
	PYTHONPATH=src ./.venv/bin/python -m uc_bench doctor

demo:
	PYTHONPATH=src ./.venv/bin/python -m uc_bench demo

status:
	./.venv/bin/python scripts/project_status.py

audit-check:
	./.venv/bin/python scripts/project_status.py --check

test:
	PYTHONPATH=src ./.venv/bin/python -m pytest

lint:
	./.venv/bin/ruff check src tests scripts

check: doctor audit-check test lint
