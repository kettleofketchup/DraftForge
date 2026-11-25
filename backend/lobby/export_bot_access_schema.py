"""Print the lobby bot access API models as a Zod bundle for zod-from-json-schema.mjs.

`just py::gen-bot-access-api [--check]` wraps this.
"""

import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    # `python -I` leaves the script's directory off sys.path.
    sys.path.append(str(BACKEND_DIR))

from common.zod_export import write_bundle, zod_bundle  # noqa: E402
from lobby.bot_access.schemas import BotAccessApi  # noqa: E402

REGEN_COMMAND = "just py::gen-bot-access-api"


def bundle() -> dict[str, Any]:
    return zod_bundle(
        BotAccessApi,
        source="backend/lobby/bot_access/schemas.py",
        regen=REGEN_COMMAND,
    )


if __name__ == "__main__":
    write_bundle(bundle())
