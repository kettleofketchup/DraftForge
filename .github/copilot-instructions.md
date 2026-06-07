# Copilot guidance for DraftForge

DraftForge is a platform for managing Dota 2 tournaments, teams, and competitive gaming. Django REST + Daphne (Channels) backend; React + TypeScript + Vite frontend; Redis for cache; everything runs through Docker Compose driven by `just`.

## Repo-wide rules

- **Task runner is `just`.** Never invoke `pytest`, `python manage.py`, or `npm test` directly in CI / scripts / docs. Always go through a `just` recipe (e.g., `just test::run '<cmd>'`, `just db::makemigrations <app>`, `just dev::debug`). The venv auto-activates.
- **WebSockets share the HTTP URL.** Daphne / Channels routes both protocols on the same `/api/...` path — there is no `/ws/...` namespace. WebSocket routes live in `backend/app/routing.py`; the frontend connects to the same path with `protocol = ws|wss`.
- **No secrets in this repo.** `.env` files are excluded; never propose committing one.
- **Frontend stack is Vite + React Router v7 (NOT Next.js).** Server Components do not apply; everything is a Client Component.

## Project conventions (canonical: `.claude/skills/`)

Each rule set below is canonical at `.claude/skills/<name>/SKILL.md`. The matching `.github/instructions/<name>.instructions.md` files contain short summaries scoped via `applyTo:` so Copilot's PR review picks up the right rules for each file path.

| Skill | Canonical | Scope (Copilot `applyTo`) |
|-------|-----------|---------------------------|
| Backend caching | `.claude/skills/django-redis-caching/SKILL.md` | `backend/**/*.py` |
| Backend logging | `.claude/skills/logging/SKILL.md` | `backend/**/*.py` (excl. management commands) |
| Brand / theming | `.claude/skills/brand/SKILL.md` (+ `docs/THEMING-GUIDE.md`) | `frontend/app/components/**`, `routes/**`, `features/**`, `app.css` |
| React patterns | global `react` skill | `frontend/**/*.{ts,tsx}` |
| shadcn/ui | global `shadcn` skill (+ `frontend/components.json`) | `frontend/app/components/**/*.{ts,tsx}` |
| Zustand stores | global `zustand` skill | `frontend/app/store/**/*.ts` |

Update the canonical skill first; mirror the relevant bullets into the `.instructions.md` file in the same PR.

## What review comments should look like

- Cite the rule by skill name (e.g., "brand: raw `<button>` — use `<PrimaryButton>`") so the author knows which canonical source to consult.
- Prefer concrete fixes over abstract guidance. If the rule has a substitution table (brand), use the named replacement.
- Don't comment on `package.json`, lockfiles, log files, or SVGs — Copilot already skips these.
