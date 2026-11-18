"""Print the message registry as a Zod bundle for zod-from-json-schema.mjs.

    python -I backend/notifications/export_schema.py | \\
        node frontend/scripts/zod-from-json-schema.mjs --out <ts> [--check]

`just py::gen-message-types [--check]` wraps this.
"""

import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    # `python -I` leaves the script's directory off sys.path.
    sys.path.append(str(BACKEND_DIR))

from common.zod_export import write_bundle, zod_bundle  # noqa: E402
from notifications.registry import REGISTRY, MessageRegistry  # noqa: E402

REGEN_COMMAND = "just py::gen-message-types"


def bundle() -> dict[str, Any]:
    return zod_bundle(
        MessageRegistry,
        source="backend/notifications/registry.py",
        regen=REGEN_COMMAND,
        data=REGISTRY,
        data_name="MESSAGE_REGISTRY",
    )


if __name__ == "__main__":
    write_bundle(bundle())
