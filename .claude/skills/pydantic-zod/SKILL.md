---
name: pydantic-zod
description: Generate frontend Zod schemas from backend pydantic models (zod_export.py + zod-from-json-schema.mjs). Use when a backend type, enum or catalogue must be shared with the frontend.
---

# Pydantic → Zod bindings

Define a shared type once as pydantic models in `backend/`; generate a committed
`*.generated.ts` with Zod schemas, inferred types and (optionally) the data itself.
Never hand-write a Zod schema that mirrors a backend model, and never hand-edit a
generated file.

Background, diagram and limits: `docs/development/pydantic-zod.md`.
Worked example: `backend/notifications/registry.py` → `export_schema.py` →
`just py::gen-message-types` → `frontend/app/lib/notifications/messageTypes.generated.ts`.

## Pipeline

```
<pkg>/export_schema.py  --(JSON bundle on stdout)-->  frontend/scripts/zod-from-json-schema.mjs --out X.generated.ts [--check]
  uses common.zod_export.zod_bundle()                  json-schema-to-zod + frontend Prettier config
```

## Add a binding

1. **Models** (Django-free module so `python -I` can import it). Use this base config:

    ```python
    class Base(BaseModel):
        model_config = ConfigDict(
            frozen=True,
            extra="forbid",                     # -> .strict()
            alias_generator=to_camel,           # camelCase keys in TS
            validate_by_name=True,
            validate_by_alias=True,
            json_schema_serialization_defaults_required=True,  # defaults stay required
        )
    ```

    - Put constraints in types so they reach Zod: `Annotated[str, StringConstraints(min_length=1, pattern=r"\S")]`,
      `Annotated[tuple[X, ...], Field(min_length=1)]`, `StrEnum` for closed sets.
    - Define one root model covering everything the frontend needs; its class name
      becomes `<Name>Schema`/`type <Name>`, as does every nested model and enum. Name
      classes for how they read in TypeScript.
    - Don't put defaults on fields typed as another model or enum (it yields `$ref` +
      `default`, which the converter rejects).

2. **Exporter** `backend/<pkg>/export_schema.py`, modelled on `backend/notifications/export_schema.py`:
   the `sys.path.append(BACKEND_DIR)` shim (for `-I`), then
   `write_bundle(zod_bundle(Root, source=..., regen="just py::gen-<thing>", data=INSTANCE, data_name="UPPER_NAME"))`.
   Omit `data`/`data_name` for schema-only bindings.

3. **Recipe** in `just/py.just`, copying `gen-message-types` (takes `*args` so `--check` passes through).

4. **Generate and commit** the `.generated.ts` with the model change:

    ```bash
    just py::gen-<thing>
    ```

5. **CI**: add `just py::gen-<thing> --check` beside the message-types step in the
   `unit` job of `.github/workflows/playwright.yml` (the job with the poetry venv and
   node). Not `just/ci.just`; those recipes run without `.venv`.

6. **Tests**
    - Backend (plain `unittest.TestCase`, runs under `just test::run 'python manage.py test <pkg> -v 2'`):
      bundle shape; every object `$def` has `required == properties` and
      `additionalProperties is False`; the exporter runs under `sys.executable -I`.
    - Frontend Vitest beside the generated file: `RootSchema.parse(DATA)` round-trips,
      constraint violations fail `safeParse`, enum `.options` match the data.

## Consume in the frontend

- Import schemas/types/data from the generated module; enum values are `XSchema.options`.
- Derive form schemas with `.pick()` / `.extend()` rather than copying fields (see the
  `zod-form-validation` skill).
- Validate API responses with the generated schema at the boundary (`Schema.parse`).

## What does not reach Zod

`@model_validator` / `@field_validator` logic, cross-entry rules and computed fields.
If the frontend must enforce one, add it in a hand-written module that wraps the
generated schema (`.superRefine`) and cover it with Vitest. Keep the generated file pure.

## Troubleshooting

| Symptom | Fix |
|---|---|
| `--check`: `X is stale; run \`just py::gen-…\`` | Run the recipe, commit the regenerated file. |
| `recursive schemas are not supported` | Converter emits plain consts; flatten the model or reference by key. |
| `$ref with sibling keywords default` | Remove the default from that model/enum-typed field. |
| `unsupported $ref` / `unknown $ref` | Only `#/$defs/*` refs work; keep all types under one root model. |
| `root schema needs a title` / clashes with a `$def` | Root must be a named model distinct from nested ones. |
| Optional `field?:` in TS for a defaulted field | Missing `json_schema_serialization_defaults_required=True`. |
| `Cannot find package 'prettier-plugin-…'` | `npm --prefix frontend ci`; the script resolves plugins from `frontend/.prettierrc`. |
| `ModuleNotFoundError: pydantic` | Use the venv python (`{{python}}` in `py.just`), not system `python3`. |
| Generated text changed after a dependency bump | `json-schema-to-zod` is pinned exactly; regenerate deliberately on upgrade. |

## Changing the converter

`frontend/scripts/zod-from-json-schema.mjs` (+ `.d.mts` types) is shared by every
binding. Extend `frontend/tests/unit/zod-from-json-schema.test.ts` first, then
regenerate every `*.generated.ts` produced by it (`git grep -l zod-from-json-schema just/`)
and confirm each `--check` passes. Bump `BUNDLE_VERSION` in both halves when the
bundle format changes.
