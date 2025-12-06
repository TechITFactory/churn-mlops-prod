.PHONY: help setup lint lint-fix format format-check test data features labels train promote batch all

help:
	@echo "Targets:"
	@echo "  setup         - install dev + api deps"
	@echo "  lint          - ruff check"
	@echo "  lint-fix      - ruff auto-fix (imports etc.)"
	@echo "  format        - black format"
	@echo "  format-check  - black --check"
	@echo "  test          - pytest"
	@echo "  data          - generate + validate + prepare"
	@echo "  features      - build features"
	@echo "  labels        - build labels + training set"
	@echo "  train         - train baseline + candidate"
	@echo "  promote       - promote best model"
	@echo "  batch         - batch score using production model"
	@echo "  all           - full local run"

setup:
	pip install -r requirements/dev.txt
	@if [ -f requirements/api.txt ]; then pip install -r requirements/api.txt; fi
	pip install -e .

lint:
	ruff check .

lint-fix:
	ruff check . --fix

format:
	black .

format-check:
	black --check .

test:
	pytest -q

data:
	./scripts/generate_data.sh
	./scripts/validate_data.sh
	./scripts/prepare_data.sh

features:
	./scripts/build_features.sh

labels:
	./scripts/build_labels.sh
	./scripts/build_training_set.sh

train:
	./scripts/train_baseline.sh
	./scripts/train_candidate.sh

promote:
	./scripts/promote_model.sh

batch:
	./scripts/batch_score.sh

all: data features labels train promote batch test lint
