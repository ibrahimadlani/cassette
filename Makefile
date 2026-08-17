.PHONY: help install lint format types test run fuzz shrink regress traces web demo bench gif clean

PYTHON ?= python3
VENV   := .venv
BIN    := $(VENV)/bin

help:
	@grep -E '^[a-z-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

install: ## create the virtualenv and install the project with dev extras
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install --upgrade pip
	$(BIN)/pip install -e ".[dev]"

lint: ## run ruff over the whole tree
	$(BIN)/ruff check .
	$(BIN)/ruff format --check .

format: ## rewrite the tree with ruff format
	$(BIN)/ruff check --fix .
	$(BIN)/ruff format .

types: ## run mypy in strict mode
	$(BIN)/mypy

test: ## run the test suite with coverage
	$(BIN)/pytest --cov --cov-report=term-missing

run: ## run one simulation (make run SEED=8421)
	$(BIN)/cassette run --seed $(or $(SEED),8421)

fuzz: ## explore seeds looking for a violation (make fuzz SEEDS=10000)
	$(BIN)/cassette fuzz --seeds $(or $(SEEDS),2000) --workers 8 --all

shrink: ## reduce a failing seed to a minimal scenario (make shrink SEED=6)
	$(BIN)/cassette shrink --seed $(or $(SEED),6)

regress: ## replay every seed in the regression corpus
	$(BIN)/cassette regress

traces: ## rebuild the traces the web replayer serves
	$(BIN)/python scripts/build_traces.py

web: ## build the web replayer
	cd web && npm ci && npm test && npm run build

demo: ## the whole story in one command
	@echo "\n== 2000 scenarios against the current store =="
	@$(BIN)/cassette fuzz --seeds 2000 --workers 8 --all --no-record || true
	@echo "\n== the same fuzzer with the fixed defects switched back on =="
	@$(BIN)/cassette fuzz --seeds 2000 --workers 8 --buggy --no-record || true
	@echo "\n== reducing one of them =="
	@$(BIN)/cassette shrink --seed 6 --buggy

bench: ## measure the numbers the README publishes
	$(BIN)/python scripts/benchmark.py

gif: ## re-record the README demo from real command output
	PATH="$(PWD)/$(BIN):$$PATH" $(BIN)/python scripts/record_demo.py

clean: ## remove caches and build artefacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov build dist web/dist
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
