"""Write the message registry as TypeScript + Zod for the frontend.

    python -I backend/notifications/export_schema.py [--out PATH] [--check]

--check compares instead of writing and exits 1 with a diff when stale.
Output is formatted the way Prettier would, so the file passes prettier --check.
"""

import argparse
import difflib
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    # `python -I` leaves the script's directory off sys.path.
    sys.path.append(str(BACKEND_DIR))

from notifications.registry import (  # noqa: E402
    GROUPS,
    MESSAGE_TYPES,
    Audience,
    Channel,
    GroupKey,
    MessageKey,
    validate_registry,
)

DEFAULT_OUT = (
    BACKEND_DIR.parent
    / "frontend"
    / "app"
    / "lib"
    / "notifications"
    / "messageTypes.generated.ts"
)
REGEN_COMMAND = "just py::gen-message-types"
PRINT_WIDTH = 80
INDENT = "  "
# Prettier never breaks after `key:` when the key is narrower than tabWidth + 3.
SHORT_KEY_WIDTH = len(INDENT) + 3

HEADER = f"""\
// GENERATED FILE - DO NOT EDIT.
// Source: backend/notifications/registry.py
// Regenerate with: {REGEN_COMMAND}
import {{ z }} from 'zod';
"""

SCHEMAS = """\
export const MessageChannelSchema = z.enum(MESSAGE_CHANNELS);
export type MessageChannel = z.infer<typeof MessageChannelSchema>;

export const MessageAudienceSchema = z.enum(MESSAGE_AUDIENCES);
export type MessageAudience = z.infer<typeof MessageAudienceSchema>;

export const MessageGroupKeySchema = z.enum(MESSAGE_GROUP_KEYS);
export type MessageGroupKey = z.infer<typeof MessageGroupKeySchema>;

export const MessageKeySchema = z.enum(MESSAGE_KEYS);
export type MessageKey = z.infer<typeof MessageKeySchema>;

export const MessageGroupSchema = z.object({
  key: MessageGroupKeySchema,
  label: z.string().min(1),
  description: z.string().min(1),
  optOutableDefault: z.boolean(),
  essentialLocked: z.boolean(),
});
export type MessageGroup = z.infer<typeof MessageGroupSchema>;

export const MessageTypeSchema = z.object({
  key: MessageKeySchema,
  group: MessageGroupKeySchema,
  label: z.string().min(1),
  description: z.string().min(1),
  audience: MessageAudienceSchema,
  channels: z.array(MessageChannelSchema).min(1),
  essentialDefault: z.boolean(),
  essentialLocked: z.boolean(),
  urgent: z.boolean(),
});
export type MessageType = z.infer<typeof MessageTypeSchema>;
"""


def ts_string(value: str) -> str:
    """Quote like Prettier with singleQuote: single unless that needs more escapes."""
    quote = '"' if value.count("'") > value.count('"') else "'"
    escaped = (
        value.replace("\\", "\\\\")
        .replace(quote, "\\" + quote)
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )
    return f"{quote}{escaped}{quote}"


def ts_value(value: str | bool | Sequence[str]) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, str):
        return ts_string(value)
    return "[" + ", ".join(ts_string(v) for v in value) + "]"


def const_array(name: str, values: Iterable[str]) -> str:
    items = [ts_string(v) for v in values]
    one_line = f"export const {name} = [{', '.join(items)}] as const;"
    if len(one_line) <= PRINT_WIDTH:
        return one_line + "\n"
    body = "".join(f"{INDENT}{item},\n" for item in items)
    return f"export const {name} = [\n{body}] as const;\n"


def object_literal(fields: Sequence[tuple[str, str | bool | Sequence[str]]]) -> str:
    pad = INDENT * 2
    lines = [f"{INDENT}{{\n"]
    for name, value in fields:
        rendered = ts_value(value)
        line = f"{pad}{name}: {rendered},"
        breakable = isinstance(value, str) and len(name) >= SHORT_KEY_WIDTH
        if len(line) > PRINT_WIDTH and breakable:
            lines.append(f"{pad}{name}:\n{pad}{INDENT}{rendered},\n")
        else:
            lines.append(line + "\n")
    lines.append(f"{INDENT}}},\n")
    return "".join(lines)


def object_array(name: str, type_name: str, objects: Iterable[str]) -> str:
    return f"export const {name}: readonly {type_name}[] = [\n{''.join(objects)}];\n"


def render() -> str:
    errors = validate_registry(GROUPS, MESSAGE_TYPES)
    if errors:
        raise ValueError("invalid message registry:\n" + "\n".join(errors))
    groups = object_array(
        "MESSAGE_GROUPS",
        "MessageGroup",
        (
            object_literal(
                (
                    ("key", g.key.value),
                    ("label", g.label),
                    ("description", g.description),
                    ("optOutableDefault", g.opt_outable_default),
                    ("essentialLocked", g.essential_locked),
                )
            )
            for g in GROUPS
        ),
    )
    types = object_array(
        "MESSAGE_TYPES",
        "MessageType",
        (
            object_literal(
                (
                    ("key", m.key.value),
                    ("group", m.group.value),
                    ("label", m.label),
                    ("description", m.description),
                    ("audience", m.audience.value),
                    ("channels", [c.value for c in m.channels]),
                    ("essentialDefault", m.essential_default),
                    ("essentialLocked", m.essential_locked),
                    ("urgent", m.urgent),
                )
            )
            for m in MESSAGE_TYPES
        ),
    )
    consts = "".join(
        (
            const_array("MESSAGE_CHANNELS", (c.value for c in Channel)),
            const_array("MESSAGE_AUDIENCES", (a.value for a in Audience)),
            const_array("MESSAGE_GROUP_KEYS", (g.value for g in GroupKey)),
            const_array("MESSAGE_KEYS", (k.value for k in MessageKey)),
        )
    )
    return "\n".join((HEADER, consts, SCHEMAS, groups, types))


def check(out: Path, expected: str) -> int:
    try:
        current = out.read_text(encoding="utf-8")
    except FileNotFoundError:
        current = ""
    if current == expected:
        return 0
    diff = difflib.unified_diff(
        current.splitlines(keepends=True),
        expected.splitlines(keepends=True),
        fromfile=f"{out} (committed)",
        tofile=f"{out} (from registry)",
    )
    sys.stdout.writelines(diff)
    print(f"\n{out} is stale; run `{REGEN_COMMAND}`.", file=sys.stderr)
    return 1


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    expected = render()
    if args.check:
        return check(args.out, expected)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(expected)
    return 0


if __name__ == "__main__":
    sys.exit(main())
