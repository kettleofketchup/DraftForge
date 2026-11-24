"""Print the Steam verification API models as a Zod bundle for zod-from-json-schema.mjs.

    python -I backend/app/export_steam_verification_schema.py | \\
        node frontend/scripts/zod-from-json-schema.mjs --out <ts> [--check]

`just py::gen-steam-verification [--check]` wraps this.
"""

import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    # `python -I` leaves the script's directory off sys.path.
    sys.path.append(str(BACKEND_DIR))

from app.steam_verification_schemas import SteamVerificationApi  # noqa: E402
from common.zod_export import write_bundle, zod_bundle  # noqa: E402

REGEN_COMMAND = "just py::gen-steam-verification"


def bundle() -> dict[str, Any]:
    return zod_bundle(
        SteamVerificationApi,
        source="backend/app/steam_verification_schemas.py",
        regen=REGEN_COMMAND,
    )


if __name__ == "__main__":
    write_bundle(bundle())
