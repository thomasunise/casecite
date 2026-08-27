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
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt

# Run the API server
uvicorn app.main:app --reload --port 8000
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
pytest -v
pytest --cov=app --cov-report=html  # With coverage report
```

### Linting

```bash
# From project root (same commands CI runs)
ruff check backend/app
ruff format backend/app --check
cd frontend && npm run lint && npx tsc --noEmit
```

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
5. Submit a PR with a clear description of what and why

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
MPL-2.0) are fine; GPL/AGPL/SSPL are not. `NOTICE.md` lists the bundled
third-party licenses; regenerate it when dependencies change.

## Tenant Isolation

All user-facing data is scoped by `user_id`. When adding new features:

- Pass `user_id` from the router to every service method that touches user data
- Add `user_id` metadata to vector DB entries
- Filter all database queries by `user_id`
- Write a test verifying User A cannot see User B's data

## Reporting Issues

Use GitHub Issues. Include:

- Steps to reproduce
- Expected vs actual behavior
- Python/Node versions and OS
- Relevant logs (redact any API keys)
