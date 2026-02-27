.PHONY: test-unit test-integ test-e2e test-all lint typecheck coverage clean

# Unit tests (Domain + Application only, fast)
test-unit:
	python -m pytest tests/unit/ -v --tb=short

# Integration tests (requires real services)
test-integ:
	python -m pytest tests/integration/ -v --tb=short --timeout=60

# E2E tests (full publish flow)
test-e2e:
	python -m pytest tests/e2e/ -v --tb=long --timeout=120

# All tests
test-all: test-unit test-integ

# Coverage report
coverage:
	python -m pytest tests/unit/ --cov=src/domain --cov=src/application --cov-report=term-missing --cov-fail-under=80

# Lint
lint:
	ruff check src/ tests/

# Type check
typecheck:
	mypy src/ --ignore-missing-imports

# DDD layer validation (custom script)
validate-ddd:
	@echo "Checking Domain → Infrastructure violations..."
	@violations=$$(grep -rn "from src.infrastructure\|import src.infrastructure" src/domain/ 2>/dev/null | wc -l); \
	echo "Domain → Infra violations: $$violations"; \
	if [ "$$violations" -ne 0 ]; then exit 1; fi
	@echo "Checking Domain → Application violations..."
	@violations=$$(grep -rn "from src.application\|import src.application" src/domain/ 2>/dev/null | wc -l); \
	echo "Domain → App violations: $$violations"; \
	if [ "$$violations" -ne 0 ]; then exit 1; fi
	@echo "Checking Application → Infrastructure violations..."
	@violations=$$(grep -rn "from src.infrastructure\|import src.infrastructure" src/application/ 2>/dev/null | wc -l); \
	echo "App → Infra violations: $$violations"; \
	if [ "$$violations" -ne 0 ]; then exit 1; fi
	@echo "✅ DDD Layer Rules: ALL VALID"

# Full quality gate
quality: test-unit coverage lint typecheck validate-ddd
	@echo "✅ ALL QUALITY GATES PASSED"

# Clean
clean:
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov .coverage
