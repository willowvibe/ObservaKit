# Contributing to ObservaKit

Thank you for your interest in contributing to ObservaKit! This guide will help you get started.

## Development Setup

### Prerequisites
- Python 3.10+
- Docker + Docker Compose
- Git

### 1. Clone and set up the dev environment

```bash
git clone https://github.com/willowvibe/ObservaKit.git
cd ObservaKit
python3 -m venv venv
source venv/bin/activate
pip install -r backend/requirements.txt
pip install pytest pytest-cov ruff
```

### 2. Start the infrastructure

```bash
cp .env.example .env
docker-compose up -d postgres prometheus grafana otel-collector
```

### 3. Run the backend locally

```bash
PYTHONPATH=. uvicorn backend.main:app --reload --port 8000
```

### 4. Run the test suite

```bash
PYTHONPATH=. pytest tests/ -v
```

## Branch Naming Convention

| Prefix | Use |
|--------|-----|
| `feat/` | New features |
| `fix/` | Bug fixes |
| `docs/` | Documentation only |
| `refactor/` | Code changes that don't add features or fix bugs |
| `test/` | Adding or updating tests |

Example: `feat/snowflake-connector`, `fix/freshness-lag-calculation`

## Pull Request Checklist

Before submitting a PR, please ensure:

- [ ] All existing tests pass: `pytest tests/ -v`
- [ ] New code has tests (if applicable)
- [ ] Linting passes: `ruff check .`
- [ ] Documentation is updated (if behavior changes)
- [ ] Commit messages are clear and descriptive
- [ ] PR description explains the *why*, not just the *what*

## Code Style

- We use [Ruff](https://docs.astral.sh/ruff/) for linting and formatting
- Line length: 100 characters
- Follow existing patterns in the codebase
- Use type hints where practical

## Good First Issues

Look for issues labeled `good first issue` on the [Issues page](https://github.com/willowvibe/ObservaKit/issues). These are great starting points:

- Add a new warehouse connector
- Add a Grafana dashboard for a new use case
- Write a quality check template for a common schema
- Improve documentation or quickstart clarity

## Reporting Bugs

When reporting bugs, please include:
1. Steps to reproduce
2. Expected behavior
3. Actual behavior
4. Environment (OS, Python version, Docker version)

## Questions?

Open a [Discussion](https://github.com/willowvibe/ObservaKit/discussions) for questions that aren't bug reports or feature requests.
