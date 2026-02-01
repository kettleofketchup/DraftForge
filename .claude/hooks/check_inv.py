#!/usr/bin/env python3
"""
Check for inv/invoke commands that should use just instead.

The project has migrated from Python Invoke to Just command runner.
Just auto-activates the venv and uses :: instead of . for namespaces.

Examples:
  inv db.migrate.all           → just db::migrate::all
  inv test.up                  → just test::up
  . .venv/bin/activate && inv  → just (no venv needed)
"""

import json
import re
import sys

# Patterns to match inv/invoke commands
INV_PATTERN = re.compile(r"\b(inv|invoke)\s+([\w.:-]+)(\s+.*)?")

# Pattern to detect venv activation (which is unnecessary with just)
VENV_ACTIVATE_PATTERN = re.compile(r"\.\s+\.?venv/bin/activate\s*&&\s*")


def convert_task_to_just(task: str) -> str:
    """Convert inv task syntax to just syntax (. → ::)."""
    return task.replace(".", "::")


def check(command: str) -> None:
    """Check command and block if it uses inv/invoke."""
    match = INV_PATTERN.search(command)
    if not match:
        return

    inv_cmd = match.group(1)  # 'inv' or 'invoke'
    task = match.group(2)  # e.g., 'db.migrate.all'
    args = match.group(3) or ""  # any additional arguments

    just_task = convert_task_to_just(task)

    # Check if there's a cd prefix we should preserve
    cd_match = re.match(r"^(cd\s+\S+\s*&&\s*)", command)
    cd_prefix = cd_match.group(1) if cd_match else ""

    # Build the suggested just command
    just_cmd = f"just {just_task}{args.rstrip()}"
    suggestion = f"{cd_prefix}{just_cmd}" if cd_prefix else just_cmd

    # Check if venv activation was in the command
    has_venv = VENV_ACTIVATE_PATTERN.search(command)

    cmd_display = command[:200] + ("..." if len(command) > 200 else "")

    lines = [
        "=" * 60,
        "BLOCKED: Python Invoke command detected",
        "=" * 60,
        "",
        f"Pattern:  {inv_cmd} {task}",
        f"Command:  {cmd_display}",
        "",
        "Problem:  This project has migrated from Invoke to Just",
        f"Solution: Use '{just_cmd}' instead",
        "",
        "Suggested alternative:",
        f"  {suggestion}",
        "",
    ]

    if has_venv:
        lines.extend(
            [
                "Note: Just auto-activates the venv, so you don't need to",
                "source .venv/bin/activate before running just commands.",
                "",
            ]
        )

    lines.extend(
        [
            "Why: This project uses Just instead of Python Invoke.",
            "Just uses :: for namespaces (not .) and auto-activates venv.",
            "",
            "Run 'just --list --list-submodules' to see all available commands.",
        ]
    )

    print("\n".join(lines), file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    try:
        data = json.loads(sys.stdin.read())
        tool_name = data.get("tool_name", "")
        if tool_name != "Bash":
            sys.exit(0)

        command = data.get("tool_input", {}).get("command", "")
        if command:
            check(command)
    except SystemExit:
        raise
    except Exception:
        pass
    sys.exit(0)
