"""Pydantic -> Zod binding: the Python half.

`zod_bundle()` turns a root model and an optional instance of it into the JSON
bundle that `frontend/scripts/zod-from-json-schema.mjs` renders as TypeScript.
No Django imports, so exporters can run with `python -I`.
See docs/development/pydantic-zod.md.
"""

import json
import sys
from typing import Any, TextIO

from pydantic import BaseModel

BUNDLE_VERSION = 1


def zod_bundle(
    model: type[BaseModel],
    *,
    source: str,
    regen: str,
    data: BaseModel | None = None,
    data_name: str | None = None,
) -> dict[str, Any]:
    if (data is None) != (data_name is None):
        raise ValueError("data and data_name go together")
    if data is not None and not isinstance(data, model):
        raise TypeError(f"data must be a {model.__name__}")
    bundle: dict[str, Any] = {
        "version": BUNDLE_VERSION,
        "source": source,
        "regen": regen,
        "schema": model.model_json_schema(by_alias=True, mode="serialization"),
    }
    if data is not None:
        bundle["data"] = {
            "name": data_name,
            "type": model.__name__,
            "value": data.model_dump(mode="json", by_alias=True),
        }
    return bundle


def write_bundle(bundle: dict[str, Any], out: TextIO = sys.stdout) -> None:
    json.dump(bundle, out, indent=2, ensure_ascii=False)
    out.write("\n")
