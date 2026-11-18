# Generated bindings: pydantic → Zod

Use when the backend payload is (or will be) a pydantic model. You get a committed
`*.generated.ts` with Zod schemas and `z.infer` types, and CI fails when it goes stale.

Background and limits: `docs/development/pydantic-zod.md`.
Tooling: `backend/common/zod_export.py` (Python half) and
`frontend/scripts/zod-from-json-schema.mjs` (TS half, `--out`, `--check`, `--in`).
Worked example (static catalogue): `backend/notifications/` → `just py::gen-message-types`.

## 1. Models

Put them in `backend/<app>/api_schemas.py` (or `schemas.py`). The module must import no
Django, so the exporter runs under `python -I`.

```python
from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class Response(BaseModel):
    model_config = ConfigDict(json_schema_serialization_defaults_required=True)


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")


class LobbyOut(Response):
    id: int
    name: str
    created_at: datetime              # -> z.string().datetime({ offset: true })
    ends_at: datetime | None          # -> z.union([..., z.null()])
    state: Literal["open", "closed"]  # -> z.enum([...])
    tags: list[str] = []


class LobbyCreateIn(Request):
    name: str = Field(min_length=1, max_length=64)


class LobbyApi(BaseModel):            # root: one model whose $defs cover the endpoint set
    lobby: LobbyOut
    lobby_create: LobbyCreateIn
```

Rules:

- **Wire names stay snake_case**: no `alias_generator` on API models, because the frontend
  schema must match what DRF sends. (The notifications catalogue uses `to_camel`
  because it is never sent over HTTP.)
- **Responses are not strict.** A browser still running an old build must accept a new
  field, so never set `extra="forbid"` on a response model. Requests forbid extras, so
  typos fail on the backend.
- `json_schema_serialization_defaults_required=True` on response models: a defaulted
  field is always present in the output, so it must not become `field?:` in TS.
- Constraints belong in types (`Field(min_length=…)`, `Literal`, `StrEnum`) so they
  reach Zod. `@model_validator` logic does not reach Zod.
- Don't put defaults on fields typed as another model or enum; that yields `$ref` +
  `default`, which the converter rejects.
- The root model and every nested class name become TS exports
  (`LobbyOutSchema`, `type LobbyOut`), so name them for the frontend.

## 2. View

```python
body = LobbyCreateIn.model_validate(request.data)          # 400 on ValidationError
lobby = create_lobby(**body.model_dump())
return Response(LobbyOut.model_validate(lobby, from_attributes=True).model_dump(mode="json"))
```

On `ValidationError` return 400. `_bad_request` in
`backend/discordbot/internal_signup_views.py` (`{"error": "invalid_request", "detail": exc.errors()}`)
suits machine clients. For frontend callers put a readable sentence in `error` (keep
`detail` for the field list), because `extractApiError` shows `error` first.

## 3. Exporter and recipe

`backend/<app>/export_schema.py`, copied from `backend/notifications/export_schema.py`
(keep the `sys.path.append(BACKEND_DIR)` shim):

```python
write_bundle(zod_bundle(LobbyApi, source="backend/lobby/api_schemas.py", regen="just py::gen-lobby-api"))
```

Pass `data=` / `data_name=` only for static data (catalogues). API bindings are
schema-only.

`just/py.just`, copied from `gen-message-types` (keep `*args` so `--check` passes through),
writing `frontend/app/features/<feature>/api.generated.ts`. Then:

```bash
just py::gen-lobby-api           # commit the .generated.ts with the model change
```

Add `just py::gen-lobby-api --check` beside the message-types step in the `unit` job of
`.github/workflows/playwright.yml` (that job has the poetry venv and node). Not
`just/ci.just`; those recipes run without `.venv`.

## 4. Frontend

`schemas.ts` re-exports what the feature uses, so call sites never import the generated
path directly:

```ts
export { LobbyOutSchema, type LobbyOut, type LobbyCreateIn } from './api.generated';
```

`api.ts` parses with the generated schema exactly as in SKILL.md. Derive form schemas
from the request schema (`LobbyCreateInSchema.extend({...})`) instead of copying fields.

## 5. Tests

- Backend: `Model.model_validate(client.get(url).json())` in the view test; exporter
  runs under `sys.executable -I` (copy `ExporterTest.test_script_runs_isolated`).
- Frontend: a realistic body parses; a missing field fails `safeParse`.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `X is stale; run \`just py::gen-…\`` | Run the recipe; commit the regenerated file. |
| `$ref with sibling keywords default` | Drop the default on that model/enum-typed field. |
| `recursive schemas are not supported` | Flatten, or reference by id. |
| `unknown $ref` / `unsupported $ref` | Every type must hang off the one root model. |
| `field?:` for a field the backend always sends | Missing `json_schema_serialization_defaults_required`. |
| Old clients fail after a backend field was added | A response model has `extra="forbid"`; remove it. |
| `Cannot find package 'prettier-plugin-…'` | `npm --prefix frontend ci`. |
| `ModuleNotFoundError: pydantic` / `django` | Use the venv python; keep the schema module Django-free. |

Changing the converter itself: extend `frontend/tests/unit/zod-from-json-schema.test.ts`
first, regenerate every binding (`git grep -l zod-from-json-schema just/`), and bump
`BUNDLE_VERSION` in both halves if the bundle format changes.
