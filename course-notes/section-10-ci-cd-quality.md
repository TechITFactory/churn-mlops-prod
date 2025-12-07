# Section 10: CI/CD & Code Quality

## Goal

Establish code quality standards, automated testing, and continuous integration practices for production-ready MLOps.

---

## Code Quality Tools

### 1. Ruff (Linter)

**File**: `ruff.toml`

```toml
line-length = 100
select = ["E", "F", "I", "B", "UP"]
ignore = ["E501"]
```

**Rules**:
- **E**: PEP 8 errors (indentation, whitespace)
- **F**: Pyflakes (unused imports, undefined variables)
- **I**: isort (import sorting)
- **B**: flake8-bugbear (common bugs)
- **UP**: pyupgrade (modern Python syntax)

**Run**:
```bash
# Check for issues
ruff check .

# Auto-fix
ruff check . --fix

# Via Makefile
make lint
make lint-fix
```

---

### 2. Black (Formatter)

**Configuration** (in `pyproject.toml`):
```toml
[tool.black]
line-length = 100
```

**Run**:
```bash
# Format all files
black .

# Check without modifying
black --check .

# Via Makefile
make format
make format-check
```

---

### 3. Pytest (Testing)

**Configuration** (in `pyproject.toml`):
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
```

**Run**:
```bash
# Run all tests
pytest

# Verbose output
pytest -v

# With coverage
pytest --cov=churn_mlops --cov-report=html

# Via Makefile
make test
```

---

## Test Structure

```
tests/
├── test_config.py          # Config loading tests
├── test_data.py            # Data generation/validation tests
├── test_features.py        # Feature engineering tests
├── test_training.py        # Training pipeline tests
├── test_api.py             # API endpoint tests
└── conftest.py             # Pytest fixtures
```

### Example Test

```python
# tests/test_config.py
from churn_mlops.common.config import load_config

def test_load_config():
    cfg = load_config()
    assert "app" in cfg
    assert "paths" in cfg
    assert cfg["app"]["name"] == "churn-mlops"

def test_config_has_required_paths():
    cfg = load_config()
    required = ["data", "raw", "processed", "features", "models", "metrics"]
    for key in required:
        assert key in cfg["paths"], f"Missing path config: {key}"
```

### API Tests

```python
# tests/test_api.py
from fastapi.testclient import TestClient
from churn_mlops.api.app import app

client = TestClient(app)

def test_live_endpoint():
    response = client.get("/live")
    assert response.status_code == 200
    assert response.json() == {"status": "live"}

def test_metrics_endpoint():
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "churn_api" in response.text
```

---

## Makefile Targets

**File**: `Makefile`

```makefile
.PHONY: help setup lint lint-fix format format-check test all

help:
    @echo "Targets:"
    @echo "  setup         - install dev + api deps"
    @echo "  lint          - ruff check"
    @echo "  lint-fix      - ruff auto-fix"
    @echo "  format        - black format"
    @echo "  format-check  - black --check"
    @echo "  test          - pytest"
    @echo "  all           - full pipeline"

setup:
    pip install -r requirements/dev.txt
    pip install -r requirements/api.txt
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

all: data features labels train promote batch test lint
```

**Usage**:
```bash
make help       # Show available targets
make setup      # Install dependencies
make lint       # Check code quality
make test       # Run tests
make all        # Full pipeline
```

---

## CI/CD Pipeline (GitHub Actions)

### File: `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  lint:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: |
          pip install --upgrade pip
          pip install ruff black
      
      - name: Lint with ruff
        run: ruff check .
      
      - name: Format check with black
        run: black --check .
  
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      
      - name: Setup Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.10'
      
      - name: Install dependencies
        run: |
          pip install -r requirements/base.txt
          pip install -r requirements/dev.txt
          pip install -e .
      
      - name: Run tests
        run: pytest -v --cov=churn_mlops
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml
  
  build-images:
    runs-on: ubuntu-latest
    needs: [lint, test]
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v3
      
      - name: Set up Docker Buildx
        uses: docker/setup-buildx-action@v2
      
      - name: Build ML image
        run: docker build -t techitfactory/churn-ml:latest -f docker/Dockerfile.ml .
      
      - name: Build API image
        run: docker build -t techitfactory/churn-api:latest -f docker/Dockerfile.api .
```

---

## Pre-commit Hooks

**File**: `.pre-commit-config.yaml`

```yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.0
    hooks:
      - id: ruff
        args: [--fix]
  
  - repo: https://github.com/psf/black
    rev: 23.0.0
    hooks:
      - id: black
  
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.4.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-yaml
      - id: check-added-large-files
```

**Setup**:
```bash
pip install pre-commit
pre-commit install

# Run manually
pre-commit run --all-files
```

**Effect**: Automatically runs linters before every `git commit`

---

## Code Review Checklist

### Before Submitting PR

- [ ] **Linter passes**: `make lint`
- [ ] **Tests pass**: `make test`
- [ ] **Format correct**: `make format-check`
- [ ] **Type hints**: Functions have return types
- [ ] **Docstrings**: Public functions documented
- [ ] **No secrets**: No hardcoded credentials
- [ ] **Config externalized**: Use `config.yaml`, not hardcoded paths

### During Code Review

- [ ] **Readability**: Clear variable names, logical structure
- [ ] **Error handling**: Exceptions caught and logged
- [ ] **Performance**: No obvious inefficiencies (e.g., nested loops on large data)
- [ ] **Security**: Input validation, no SQL injection risks
- [ ] **Tests**: New features have tests

---

## Code Coverage

```bash
# Run tests with coverage
pytest --cov=churn_mlops --cov-report=html --cov-report=term

# Open HTML report
open htmlcov/index.html
```

**Target Coverage**: > 70% for production-critical paths

**What to test**:
- ✅ Config loading
- ✅ Data validation logic
- ✅ Feature engineering logic
- ✅ API endpoints
- ⚠️ Training (slow, use small data in tests)
- ❌ Plotting/visualization (not critical)

---

## Static Type Checking (Optional)

### Mypy

```bash
# Install
pip install mypy

# Run
mypy src/churn_mlops
```

**Configuration** (in `pyproject.toml`):
```toml
[tool.mypy]
python_version = "3.10"
warn_return_any = true
warn_unused_configs = true
disallow_untyped_defs = false  # Gradually enable
```

---

## Documentation Generation

### Docstrings

```python
def build_labels(user_daily: pd.DataFrame, churn_window_days: int) -> pd.DataFrame:
    """
    Create churn labels from user daily activity.
    
    For each user-date, count future active days in the next `churn_window_days`.
    If future_active_days == 0, churn_label = 1.
    
    Args:
        user_daily: DataFrame with columns [user_id, as_of_date, is_active_day]
        churn_window_days: Forward-looking window (typically 30)
    
    Returns:
        DataFrame with columns [user_id, as_of_date, churn_label]
    
    Raises:
        ValueError: If user_daily doesn't contain 'is_active_day'
    """
    ...
```

### Auto-generated API Docs

FastAPI automatically generates OpenAPI docs:
- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

---

## Files Involved

| File | Purpose |
|------|---------|
| `ruff.toml` | Linter configuration |
| `pyproject.toml` | Project metadata, tool configs |
| `Makefile` | Common development tasks |
| `.github/workflows/ci.yml` | CI/CD pipeline |
| `.pre-commit-config.yaml` | Pre-commit hooks |
| `tests/` | Unit tests |

---

## Run Commands

```bash
# Full quality check
make lint
make format-check
make test

# Fix issues
make lint-fix
make format

# Via pre-commit
pre-commit run --all-files

# CI simulation (local)
./scripts/ci_check.sh  # (create this script)
```

---

## Troubleshooting

**Issue**: Ruff reports import errors
- **Cause**: Imports not sorted
- **Fix**: `ruff check . --fix` (auto-sorts)

**Issue**: Black format conflicts with editor
- **Cause**: Editor using different line length
- **Fix**: Configure editor to use `pyproject.toml`

**Issue**: Tests fail with `ModuleNotFoundError`
- **Cause**: Package not installed in editable mode
- **Fix**: `pip install -e .`

**Issue**: Pre-commit hooks slow
- **Cause**: Running on all files every time
- **Fix**: Only runs on changed files by default; use `--all-files` sparingly

---

## Best Practices

1. **Automate quality checks**: CI runs on every PR
2. **Fast feedback**: Pre-commit hooks catch issues before commit
3. **Test critical paths**: Don't aim for 100% coverage, focus on business logic
4. **Consistent style**: Use Black (no debates about formatting)
5. **Version control hooks**: `.pre-commit-config.yaml` in repo

---

## Next Steps

- **[Section 11](section-11-containerization-deploy.md)**: Docker and Kubernetes deployment
- **[Section 12](section-12-monitoring-retrain.md)**: Monitoring and retraining
- **[Section 02](section-02-repo-blueprint-env.md)**: Review environment setup

---

## Key Takeaways

1. **Ruff + Black** enforce consistent code style
2. **Pytest** validates business logic with fast unit tests
3. **Makefile** provides one-command shortcuts for common tasks
4. **CI/CD** catches issues before merge
5. **Pre-commit hooks** catch issues before push
