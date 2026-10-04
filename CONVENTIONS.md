# CaseCite Platform — Development Conventions

These are the conventions the codebase follows. New code should follow them;
where existing code deviates (the notes below say where), move it toward the
convention when you touch it rather than copying the deviation.

---

## Frontend Architecture (`frontend/src/`)

### File Structure

```
src/
  api/            # API client modules (one per domain, barrel via index.ts)
  components/
    shared/       # Reusable components (Icon, PdfDocumentViewer, etc.)
    modals/       # Modal dialogs (CitationModal, AuthModals, etc.)
    index.ts      # Barrel re-exports — every shared/modal component MUST be exported here
  contexts/       # React contexts (AppContext, ResearchContext)
  hooks/          # App-level hooks (effects, UI state, shortcuts) + useResearchState
  layout/         # App shell components (AppHeader, LeftSidebar, RightPanel, etc.)
  stores/         # Zustand stores (uiStore, authStore, etc.)
  views/          # Page-level view components (one per tab/route)
  utils/          # Utility functions
```

### View Files (`views/XxxView.tsx`)

- **One view component per file**: `function XxxView()` — no inline sub-components.
- Views render. They destructure state from stores/hooks and return JSX.
- **Business logic belongs in the store**: data fetching, handlers and derived data live in the corresponding Zustand store (or `useResearchState`). A view's own `useEffect` is for lifecycle wiring only — calling the store's `init()`, reacting to a route parameter, focus and scroll management.
- Views may have minimal local UI state (e.g., a dropdown open/close ref) but nothing else.
- Known deviation: `ContractsView`, `DraftingView` and `ResearchView` are larger than this rule intends and still hold some handler wiring. Extract into the store or a shared component when changing them.
- Static constants (like option arrays) may live at module scope. Components and rendering logic must not.
- If a view needs a helper component, extract it to `components/shared/` and import it.
- CSS: one `XxxView.module.css` per view, imported as `s`.
- Pass `s` (the CSS module object) as a prop to child components that need the view's styles.

**Standard view file structure:**
```tsx
import React from 'react';
import { useSomeStore } from '../stores/someStore';
import { Icon, SomeComponent } from '../components';
import s from './XxxView.module.css';

// Static constants only (no components, no rendering functions)
const OPTIONS = [ ... ] as const;

function XxxView() {
  const { stateA, stateB, handlerA, computedValue } = useSomeStore();
  // local UI refs and lifecycle wiring only — no business logic
  // return JSX
}

// Views are the one place a default export is used: routes load them with
// React.lazy(() => import('../views/XxxView')), which needs one.
export default XxxView;
```

### Hooks (`hooks/`)

- Feature state lives in Zustand stores (next section), not in per-feature hooks. `hooks/` holds the app-level hooks — `useAppEffects` (mount-time bootstrap), `useAppUIState`, `useKeyboardShortcuts` — and `useResearchState`, the one feature whose state is a hook, called at the App level and provided through context so it survives navigation.
- Do not add a new `useXxxState` hook for a feature; add a store.
- Hooks import from `../api` for backend calls. They never import view components.

### Shared Components (`components/shared/`)

- Every reusable UI component gets its own file: `ComponentName.tsx` + optional `ComponentName.module.css`.
- Every component MUST be re-exported from `components/index.ts`.
- Components receive styles from parent views via an `s` prop (Record<string, string>) when they need the parent's CSS module classes.
- Components that own their own styles import their own `.module.css`.

### Zustand Stores (`stores/`)

- One store per domain/feature. All business logic, derived state, and side effects live here.
- Stores use `useUIStore.getState().addToast()` for toasts (not passed as props).
- Stores use `useUIStore.getState().showConfirm()` for confirmation dialogs (never `window.confirm()`).
- Stores use `appNavigate` from `utils/router.ts` for navigation (never `useNavigate` — that's a hook).
- **No module-level side effects**: never call `store.getState().loadSomething()` at import time. Use a lazy `init()` method with an `_initialized` flag, called from the view's `useEffect`.
- **No native browser APIs for UI**: never use `window.confirm()`, `window.alert()`, or `window.prompt()` — use the store's modal/toast system.

### API Layer (`api/`)

- One file per domain (documents.ts, chat.ts, contracts.ts, etc.).
- All exports go through `api/index.ts` barrel.
- **Never use raw `fetch()`** — always go through `api.request()` or `api.authFetch()`.
- **Never use raw `api.request('/path')` in components** — create a typed domain method in the appropriate `api/*.ts` file and call that instead. Components and stores should only call named methods like `api.getKeyStatus()`, never `api.request('/user/keys/status')`.
- Every new domain method must also be added to the `ApiClient` interface in `api/types.ts`.
- Full URLs use `${API_BASE_URL}/path`. Relative endpoints use `/path`.
- **Never pass `api` as a prop** to components. Components import `api` directly from `../api` (or `../../api` etc.).

---

## Backend Architecture (`backend/app/`)

### File Structure

```
backend/app/
  routers/        # FastAPI APIRouter modules (one per domain)
  services/       # Business logic (one module per domain)
  models/
    db_models.py  # SQLAlchemy table definitions
    schemas.py    # Pydantic schemas and enums
  middleware/     # Security, CSRF, rate limiting
  config.py       # Pydantic settings
  database.py     # Async engine and session factory
  main.py         # App init, middleware stack, health endpoints
```

### Router Rules (`routers/`)

- One router per domain with a prefix: `APIRouter(prefix="/domain", tags=["domain"])`.
- **Route ordering matters**: literal paths MUST be defined BEFORE parameterized catch-alls.
  - Correct: `@router.get("/stats")` then `@router.get("/{id}")` then `@router.delete("/all")` then `@router.delete("/{id}")`
  - Wrong: `@router.delete("/{id}")` before `@router.delete("/all")` (the literal "/all" becomes unreachable)
- Use `Depends(get_current_user)` for auth and `require_permission("<area>.<action>")` (from `services/permissions.py`) for anything gated by role — e.g. `require_permission("admin.users")` for user administration. Do not check role names inline. (This is a self-hosted product — there is no subscription/billing tier.)
- Any endpoint that takes an id must resolve ownership server-side (owner or matter member) and answer 404, not 403, for someone else's object.
- Validate file uploads with magic bytes, not just extensions.
- Catch specific exceptions — never bare `except:`. Client libraries raise their own base classes (`httpx.HTTPError`, `openai.APIError`, `anthropic.APIError`, `chromadb.errors.ChromaError`); a tuple of built-ins does not catch them.

### Service Rules (`services/`)

- Business logic lives in services, not routers. Routers handle HTTP concerns only.
- Services are imported by routers, never the reverse.
- In-memory state (caches, sync status dicts, OAuth state) belongs in a service module, not in a router file.

### Schema Rules (`models/`)

- Pydantic request/response models belong in `models/schemas.py`, not inline in router files.
- SQLAlchemy table definitions live in per-domain modules under `models/` (e.g. `models/documents.py`, `models/matters.py`, `models/auth.py`), all inheriting from `models/base.py`.
- `models/db_models.py` is a backwards-compatibility re-export barrel only — never define new tables there. Add the model to its domain file and re-export it from `db_models.py`.

---

## General Rules

- **No monolith components**: If a function renders JSX and is more than ~10 lines, it belongs in its own file under `components/shared/`.
- **No inline rendering utilities**: Functions like markdown parsers, text formatters, or content renderers go in `components/shared/` or `utils/`.
- **Barrel exports**: Every new shared component or modal must be added to `components/index.ts`. Every new API module must be added to `api/index.ts`.
- **CSS Modules**: Always use `.module.css`. Never use global CSS or inline style objects for layout.
- **No unused state**: Don't export state/setters from hooks that nothing consumes. Clean up dead exports.
- **No duplicate state**: Never define the same state field in two stores. Search existing stores before adding new state.
- **Object URL cleanup**: Always call `URL.revokeObjectURL()` when replacing or clearing blob URLs.
- **TypeScript**: Use proper types. Avoid `any` for component props — use an interface.
- **Component placement**: Modal dialogs go in `components/modals/`. Reusable UI pieces go in `components/shared/`. Never put a modal in `shared/`.
