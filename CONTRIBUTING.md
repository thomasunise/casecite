# Contributing to CaseCite

Thank you for your interest in contributing. This guide covers the development setup and workflow.

## Development Setup

### Prerequisites

- Python 3.11+
- Node.js 20+
- Docker (optional, for full-stack testing)

### Backend

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r requirements.lock      # exact, hash-pinned runtime set (what CI and the image use)
pip install -r requirements-dev.txt   # pytest, pytest-cov, ruff, mypy, bandit, pip-audit

# Run the API server (DEBUG=true: SQLite, no Redis, auto-generated dev secrets)
DEBUG=true uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
npm run dev  # Starts Vite dev server on port 3000
```

The Vite dev server proxies `/api` requests to `localhost:8000`.

### Running Tests

```bash
cd backend
python -m pytest                    # full suite
python -m pytest tests/test_x.py    # one file

# What CI runs: the same suite with branch coverage and a 50% floor
python -m pytest tests/ --cov=app --cov-branch --cov-report=term-missing --cov-fail-under=50
```

The suite writes to a throwaway data directory, uses dummy provider keys and
blocks outbound network access (`backend/tests/conftest.py`), so it never
touches `backend/data` or a real API key. Tests must not need either.

### Linting

```bash
# From project root (same commands CI runs)
ruff check backend/app scripts
ruff format backend/app --check
mypy backend/app --ignore-missing-imports   # report-only in CI for now
cd frontend && npm run lint && npx tsc --noEmit
```

`pre-commit install` sets up the hooks in `.pre-commit-config.yaml` (ruff,
gitleaks secret scanning, private-key detection).

## Code Style

- **Python**: Follow the ruff config in `pyproject.toml` (E, F, W, I, UP, B, SIM, S rules). Max line length 100.
- **TypeScript/React**: Functional components, hooks only. CSS Modules (`.module.css` per component) with shared variables in `styles/`.
- **Commits**: Use imperative mood in commit messages. Keep them concise.

## Project Structure

- Backend services live in `backend/app/services/`. Each service is a focused module.
- The RAG pipeline is in `backend/app/services/rag/` as a package with submodules.
- API routes live in `backend/app/routers/`. One router per domain.
- Frontend components are in `frontend/src/components/`.

## Pull Request Process

1. Fork the repository and create a feature branch
2. Make your changes with tests
3. Ensure `ruff check`, `pytest`, `npm run lint`, and `npx tsc --noEmit` pass
4. Sign off every commit (see below)
5. Submit a PR against `main` with a clear description of what and why

CI must pass and a code owner (`.github/CODEOWNERS`) reviews every PR before it
is merged. Maintainers: that is enforced by branch protection on `main`, which
is a repository setting — keep "require a pull request", "require review from
Code Owners" and "require status checks" switched on.

## Developer Certificate of Origin

CaseCite is distributed under the Elastic License 2.0, and contributions are
accepted under the same terms. To keep the licensing of the codebase clean, we
use the [Developer Certificate of Origin](https://developercertificate.org/)
(DCO) rather than a CLA: by signing off a commit you certify that you wrote the
change or otherwise have the right to submit it under the project license.

Sign off with `git commit -s`, which appends a line like

```
Signed-off-by: Your Name <you@example.com>
```

to the commit message. Pull requests whose commits are not signed off will be
asked to add it (`git commit --amend -s` / `git rebase --signoff`).

## Third-party code

Do not vendor third-party source into the tree. Add dependencies to
`backend/requirements.txt` (and regenerate `requirements.lock`) or
`frontend/package.json`, and check the license is compatible with
redistribution under ELv2 — permissive licenses (MIT, BSD, Apache-2.0, ISC,
MPL-2.0) are fine; GPL/AGPL/SSPL are not.

After changing a Python dependency, regenerate the lock (the command is in the
header of `backend/requirements.lock`):

```bash
cd backend
uv pip compile requirements.txt --universal --generate-hashes --python-version 3.11 -o requirements.lock
```

`NOTICE.md` lists every bundled third-party package and its license. It is
generated — regenerate it whenever either lock file changes:

```bash
python3 scripts/generate_notice.py
```

## Tenant Isolation

All user-facing data is scoped by `user_id`. When adding new features:

- Pass `user_id` from the router to every service method that touches user data
- Add `user_id` metadata to vector DB entries
- Filter all database queries by `user_id`
- Write a test verifying User A cannot see User B's data — one that creates
  real data for both users, not one that compares two empty lists

## Reporting Issues

Security vulnerabilities go through private reporting, never a public issue —
see [SECURITY.md](SECURITY.md). For everything else, use GitHub Issues
([SUPPORT.md](SUPPORT.md) explains what belongs where). Include:

- Steps to reproduce
- Expected vs actual behavior
- Python/Node versions and OS
- Relevant logs (redact any API keys)
