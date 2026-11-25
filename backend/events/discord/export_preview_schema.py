"""Print the Discord preview API models as a Zod bundle for zod-from-json-schema.mjs.

`just py::gen-discord-preview [--check]` wraps this.
"""

import sys
import types
from pathlib import Path
from typing import Any

BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(BACKEND_DIR) not in sys.path:
    # `python -I` leaves the script's directory off sys.path.
    sys.path.append(str(BACKEND_DIR))

# events/discord/__init__.py imports Django; load preview_schema without running it.
for _name, _path in (
    ("events", BACKEND_DIR / "events"),
    ("events.discord", BACKEND_DIR / "events" / "discord"),
):
    if _name not in sys.modules:
        _package = types.ModuleType(_name)
        _package.__path__ = [str(_path)]
        sys.modules[_name] = _package

from common.zod_export import write_bundle, zod_bundle  # noqa: E402
from events.discord.preview_schema import DiscordPreviewApi  # noqa: E402

REGEN_COMMAND = "just py::gen-discord-preview"


def bundle() -> dict[str, Any]:
    return zod_bundle(
        DiscordPreviewApi,
        source="backend/events/discord/preview_schema.py",
        regen=REGEN_COMMAND,
    )


if __name__ == "__main__":
    write_bundle(bundle())
