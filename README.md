# PainSync Backend

## Test Setup

Install backend + pinned test dependencies:

```bash
python3 -m pip install -r requirements-test.txt
```

## Run Backend Tests

For local test runs, use an isolated SQLite URL and a temporary secret:

```bash
DATABASE_URL=sqlite:///./test.db SECRET_KEY=test_secret python3 -m pytest tests -q
```

Run only liquid-intake endpoint tests:

```bash
DATABASE_URL=sqlite:///./test.db SECRET_KEY=test_secret python3 -m pytest tests/test_liquid_intake_endpoints.py -q
```

## CI-Friendly Command

Use this command in CI jobs for deterministic test execution:

```bash
python3 -m pip install -r requirements-test.txt && \
DATABASE_URL=sqlite:///./test.db SECRET_KEY=test_secret python3 -m pytest tests -q
```

## GitHub Actions Example

```yaml
name: backend-tests
on: [push, pull_request]

jobs:
  test-backend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: backend
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.11'
      - name: Install dependencies
        run: python -m pip install -r requirements-test.txt
      - name: Run tests
        env:
          DATABASE_URL: sqlite:///./test.db
          SECRET_KEY: test_secret
        run: python -m pytest tests -q
```
