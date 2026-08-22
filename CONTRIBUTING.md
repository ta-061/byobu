# Contributing to byobu

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e '.[serve,dev]'
```

## Running tests

```bash
python -m unittest discover -s tests -v
```

Tests cover the diff engine (`tests/test_engine.py`), the CLI (`tests/test_cli.py`), and the web app (`tests/test_app.py`). If you add a feature, add or extend a test alongside it.

## Code style

Match the style already in the file you're editing: no type-annotation-heavy docstrings, no comments unless they explain a non-obvious *why* (a hidden constraint, a workaround, a subtle invariant). Prefer small, focused functions over speculative abstractions.

## Pull requests

- Keep PRs scoped to one change; avoid bundling unrelated refactors.
- Describe the "why" in the PR description, not just the "what".
- Make sure `python -m unittest discover -s tests -v` passes before opening the PR.
- If you touch the web UI, note in the PR description how you tested it (manual check in a browser, since there's no browser test suite).
