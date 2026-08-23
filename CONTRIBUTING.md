# Contributing to kogo

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
- If you change the public API (`kogo/__init__.py`, `compare_pdfs`'s signature or
  result shape), CLI flags, or configuration, update `docs-src/` (and
  `README.md`/`README.ja.md` if it's quickstart-relevant) in the same PR.

## Documentation site

`docs-src/` holds the [mkdocs-material](https://squidfunk.github.io/mkdocs-material/)
source for the manual published at <https://kogo.tatu-sec.dev/manual/>. The library
API reference page is generated from docstrings via
[mkdocstrings](https://mkdocstrings.github.io/) — improving a docstring improves
that page too. To preview locally:

```bash
pip install -e '.[docs]'
mkdocs serve
```

The site is built and deployed by `.github/workflows/pages.yml` on every push to
`main`; nothing under `docs/site/manual/` should be committed by hand.
