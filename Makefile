.PHONY: help install lint format types test run fuzz regress clean

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

regress: ## replay every seed in the regression corpus
	$(BIN)/cassette regress

clean: ## remove caches and build artefacts
	rm -rf .pytest_cache .mypy_cache .ruff_cache .coverage htmlcov build dist
	find . -name '__pycache__' -type d -prune -exec rm -rf {} +
