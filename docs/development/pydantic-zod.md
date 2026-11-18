# Pydantic to Zod

When the frontend needs a backend type, define it once as pydantic models and generate
the Zod schemas from them. Field constraints (`min_length`, `pattern`, enums,
`extra="forbid"`) carry over, so the frontend validates with the same rules as the
backend.

```mermaid
flowchart LR
    M[pydantic models] -->|model_json_schema| B[bundle JSON]
    D[model instance, optional] -->|model_dump| B
    B -->|stdin| C[zod-from-json-schema.mjs]
    C -->|json-schema-to-zod + prettier| T[*.generated.ts]
```

| Piece | Path |
|---|---|
| Python half | `backend/common/zod_export.py`: `zod_bundle()` and `write_bundle()` |
| TypeScript half | `frontend/scripts/zod-from-json-schema.mjs` (`--out`, `--check`, `--in`) |
| First user | `backend/notifications/export_schema.py` and `just py::gen-message-types` |

## The models

```python
from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class Base(BaseModel):
    model_config = ConfigDict(
        frozen=True,
        extra="forbid",                 # Zod .strict()
        alias_generator=to_camel,       # camelCase on the frontend
        validate_by_name=True,
        validate_by_alias=True,
        json_schema_serialization_defaults_required=True,
    )
```

`json_schema_serialization_defaults_required` matters: without it a field with a
default is optional in the schema and `field?: T | undefined` in TypeScript.

Use one root model whose `$defs` cover everything the frontend needs. It becomes
`<Title>Schema`, and each nested model or enum becomes `<Name>Schema` plus
`type <Name>`, so pick class names that read well in TypeScript.

## The exporter

Keep it free of Django imports so it runs under `python -I`:

```python
from common.zod_export import write_bundle, zod_bundle

write_bundle(
    zod_bundle(
        Registry,
        source="backend/thing/registry.py",
        regen="just py::gen-thing",
        data=REGISTRY,          # optional: emit the instance as a typed const
        data_name="THING_REGISTRY",
    )
)
```

## The recipe

```just
gen-thing *args:
    {{quote(python)}} -I {{quote(backend / "thing/export_schema.py")}} \
        | node {{quote(root / "frontend/scripts/zod-from-json-schema.mjs")}} \
            --out {{quote(root / "frontend/app/lib/thing/thing.generated.ts")}} "$@"
```

Commit the generated file and add `just py::gen-thing --check` to the `unit` job in
`.github/workflows/playwright.yml`. That job has both the poetry venv and node.

## Limits

The converter refuses what it cannot render faithfully instead of falling back to
`z.any()`:

- recursive models (a `$def` that reaches itself);
- `$ref` outside `#/$defs/`, or a `$ref` with sibling keywords such as `default`
  (a default on a field whose type is another model or an enum produces one);
- a bundle whose root schema has no `title`.

Model and field validators (`@model_validator`, `@field_validator`) do not reach Zod.
Write a Vitest test for any rule the frontend must also enforce.

`json-schema-to-zod` is pinned exactly in `frontend/package.json`: a new version can
change the generated text, and the `--check` step fails until you regenerate.
