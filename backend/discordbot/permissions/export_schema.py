import sys
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    sys.path.append(str(BACKEND_DIR))

from common.zod_export import write_bundle, zod_bundle  # noqa: E402
from discordbot.permissions.schemas import PermissionChecksApi  # noqa: E402


def bundle() -> dict[str, Any]:
    return zod_bundle(
        PermissionChecksApi,
        source="backend/discordbot/permissions/schemas.py",
        regen="just py::gen-discord-permissions-api",
    )


if __name__ == "__main__":
    write_bundle(bundle())
