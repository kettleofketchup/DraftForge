"""Write the operations notice registry as TypeScript + Zod for the frontend.

    python -I backend/opsnotices/export_schema.py [--out PATH] [--check]

--check compares instead of writing and exits 1 with a diff when stale.
Output is formatted the way Prettier would. Runs without Django: it imports
only opsnotices.registry and every backend/*/ops_notices.py.
"""

import argparse
import difflib
import importlib
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

BACKEND_DIR: Path = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    # `python -I` leaves the script's directory off sys.path.
    sys.path.append(str(BACKEND_DIR))

from opsnotices.registry import (  # noqa: E402
    NoticeCategory,
    NoticeSeverity,
    NoticeType,
    all_notice_types,
    validate_registry,
)

DEFAULT_OUT: Path = (
    BACKEND_DIR.parent
    / "frontend"
    / "app"
    / "lib"
    / "opsnotices"
    / "noticeTypes.generated.ts"
)
REGEN_COMMAND = "just py::gen-notice-types"
PRINT_WIDTH = 80
INDENT = "  "
# Prettier never breaks after `key:` when the key is narrower than tabWidth + 3.
SHORT_KEY_WIDTH = len(INDENT) + 3

# Mirrors OpsNotice.State / OpsNotice.DeliveryState; a test keeps them in step.
NOTICE_STATES: tuple[str, ...] = ("open", "resolved")
NOTICE_DELIVERY_STATES: tuple[str, ...] = (
    "pending",
    "sent",
    "partial",
    "failed",
    "unrouted",
)

HEADER = f"""\
// GENERATED FILE - DO NOT EDIT.
// Source: backend/*/ops_notices.py via backend/opsnotices/export_schema.py
// Regenerate with: {REGEN_COMMAND}
import {{ z }} from 'zod';
"""

SCHEMAS = """\
export const NoticeTypeMetaSchema = z.object({
  key: z.string(),
  label: z.string().min(1),
  description: z.string().min(1),
  category: NoticeCategorySchema,
  defaultSeverity: NoticeSeveritySchema,
  autoResolves: z.boolean(),
  dedupes: z.boolean(),
});
export type NoticeTypeMeta = z.infer<typeof NoticeTypeMetaSchema>;
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


def ts_value(value: str | bool) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return ts_string(value)


def const_array(name: str, values: Iterable[str], suffix: str = "as const") -> str:
    items = [ts_string(v) for v in values]
    one_line = f"export const {name} = [{', '.join(items)}] {suffix};"
    if not items or len(one_line) <= PRINT_WIDTH:
        return one_line + "\n"
    body = "".join(f"{INDENT}{item},\n" for item in items)
    return f"export const {name} = [\n{body}] {suffix};\n"


def enum_block(const_name: str, type_name: str, values: Iterable[str]) -> str:
    return (
        const_array(const_name, values)
        + f"export const {type_name}Schema = z.enum({const_name});\n"
        + f"export type {type_name} = z.infer<typeof {type_name}Schema>;\n"
    )


def object_literal(fields: Sequence[tuple[str, str | bool]]) -> str:
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


def type_meta(notice_type: NoticeType[Any]) -> str:
    return object_literal(
        (
            ("key", notice_type.key),
            ("label", notice_type.label),
            ("description", notice_type.description),
            ("category", notice_type.category.value),
            ("defaultSeverity", notice_type.default_severity.value),
            ("autoResolves", notice_type.auto_resolves),
            ("dedupes", notice_type.dedupe_key is not None),
        )
    )


def render(types: list[NoticeType[Any]]) -> str:
    ordered = sorted(types, key=lambda t: t.key)
    severities = sorted(NoticeSeverity, key=lambda s: s.rank)
    enums = "\n".join(
        (
            enum_block(
                "NOTICE_CATEGORIES", "NoticeCategory", (c.value for c in NoticeCategory)
            ),
            enum_block(
                "NOTICE_SEVERITIES", "NoticeSeverity", (s.value for s in severities)
            ),
            enum_block("NOTICE_STATES", "NoticeState", NOTICE_STATES),
            enum_block(
                "NOTICE_DELIVERY_STATES", "NoticeDeliveryState", NOTICE_DELIVERY_STATES
            ),
        )
    )
    keys = const_array(
        "NOTICE_KEYS",
        (t.key for t in ordered),
        suffix="as const satisfies readonly string[]",
    )
    head = "export const NOTICE_TYPES: readonly NoticeTypeMeta[] = ["
    if ordered:
        notice_types = f"{head}\n{''.join(type_meta(t) for t in ordered)}];\n"
    else:
        notice_types = f"{head}];\n"
    return "\n".join((HEADER, enums, keys, SCHEMAS, notice_types))


def discover() -> list[str]:
    names = sorted(
        f"{path.parent.name}.ops_notices"
        for path in BACKEND_DIR.glob("*/ops_notices.py")
    )
    for name in names:
        importlib.import_module(name)
    return names


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
    discover()
    validate_registry()
    expected = render(all_notice_types())
    if args.check:
        return check(args.out, expected)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(expected)
    return 0


if __name__ == "__main__":
    sys.exit(main())
