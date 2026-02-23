# Contributing to human.md

Thank you for considering contributing to human.md. This project exists because
developers care about sustainable work patterns, and every contribution matters.

## Prerequisites

- **Python 3.9+** and/or **Node 18+** (one is enough; both are better for full test coverage)
- **jq** — for JSON manipulation in shell scripts
- **ShellCheck** — for linting shell scripts (optional, but CI runs it)

## Development Setup

```bash
git clone https://github.com/thellmwhisperer/human.md.git
cd human.md

# Python
python -m venv .venv
source .venv/bin/activate
pip install pytest ruff

# Node (no install needed — zero dependencies)
```

## Running Tests

```bash
# Unit tests (Python + Node)
make test

# Individual suites
make test-python
make test-node

# E2E (requires jq — uses sandboxed HOME, safe to run locally)
make test-e2e

# Linting
make lint
```

## Code Style

- **Python**: Follows [ruff](https://docs.astral.sh/ruff/) defaults with a 120-char line limit. Run `ruff check` before committing.
- **Shell**: Must pass [ShellCheck](https://www.shellcheck.net/). Run `shellcheck <file>` before committing.
- **JavaScript**: Standard ES module style. No transpilers, no bundlers.

## Project Structure

```text
guard/          Core enforcement logic (Python + Node implementations)
spec/           Specification document
templates/      User-facing templates
examples/       Example configurations
tests/          Unit and E2E tests
docs/           Background documentation
install.sh      Interactive installer
uninstall.sh    Clean uninstaller
```

## Dual Implementation

The core logic exists in both `guard/core.py` and `guard/core.mjs`. These must
stay functionally identical. If you change behavior in one, change it in both
and ensure both test suites pass.

## Making Changes

1. Fork the repository
2. Create a branch from `main` (`feat/description` or `fix/description`)
3. Write a test that covers your change
4. Implement the change
5. Ensure all tests pass (`make test`)
6. Ensure linting passes (`make lint`)
7. Open a pull request against `main`

## Commit Messages

Use [Conventional Commits](https://www.conventionalcommits.org/):

- `feat:` — new functionality
- `fix:` — bug fix
- `docs:` — documentation only
- `test:` — test additions or corrections
- `ci:` — CI/CD changes

Keep messages short and descriptive.

## Versioning

This project follows [Semantic Versioning](https://semver.org/). Version bumps
are determined by the type of change:

- `fix:` → **patch** (1.1.0 → 1.1.1)
- `feat:` → **minor** (1.1.0 → 1.2.0)
- Breaking changes → **major** (1.1.0 → 2.0.0)

Every PR that changes runtime behavior must:

1. Bump `version` in both `pyproject.toml` and `package.json`
2. Add an entry to `CHANGELOG.md` under the new version

On merge to main, the CI creates a GitHub Release automatically from the
version in `pyproject.toml`. If the version wasn't bumped, no release is created.

## Design Principles

- **Zero external dependencies** in production code. The core must run with stdlib only.
- **Graceful degradation**. Errors must never break the user's workflow. If something fails, pass through.
- **Dual runtime parity**. Python and Node implementations must behave identically.
- **TDD**. Tests come before implementation.

## Reporting Issues

Use the [issue templates](https://github.com/thellmwhisperer/human.md/issues/new/choose).
Include your OS, shell, runtime version, and the output of `install.sh` if relevant.
