"""Print the MMR summary models as a Zod bundle for zod-from-json-schema.mjs.

    python -I backend/org/mmr_requests/export_schema.py | \\
        node frontend/scripts/zod-from-json-schema.mjs --out <ts> [--check]

`just py::gen-mmr-summary-types [--check]` wraps this.
"""

import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    # `python -I` leaves the script's directory off sys.path.
    sys.path.append(str(BACKEND_DIR))

from common.zod_export import write_bundle, zod_bundle  # noqa: E402
from org.mmr_requests.schemas import UserMmrSummary  # noqa: E402

REGEN_COMMAND = "just py::gen-mmr-summary-types"


def bundle() -> dict[str, Any]:
    return zod_bundle(
        UserMmrSummary,
        source="backend/org/mmr_requests/schemas.py",
        regen=REGEN_COMMAND,
    )


if __name__ == "__main__":
    write_bundle(bundle())
