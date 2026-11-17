"""Message registry invariants and the TS/Zod exporter.

Plain unittest so the module also runs without Django:
`python -m unittest notifications.tests.test_registry` from backend/.
"""

import io
import os
import re
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import replace
from pathlib import Path
from unittest import TestCase

from notifications import export_schema
from notifications.registry import (
    CONDUCT_GROUP,
    GROUPS,
    MESSAGE_TYPES,
    Audience,
    Channel,
    GroupKey,
    MessageGroup,
    MessageKey,
    MessageType,
    get_group,
    get_message_type,
    types_in_group,
    validate_registry,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND_DIR / "notifications" / "export_schema.py"

SEEDED_KEYS = {
    "rsvp.signup_receipt",
    "rsvp.reachability_check",
    "rsvp.promotion",
    "rsvp.roster_change",
    "rsvp.event_cancelled",
    "rsvp.confirm_request",
    "rsvp.escalation_nudge",
    "rsvp.drop_notice",
    "rsvp.pre_game_reminder",
    "event.profile_reminder",
    "event.attendance_reminder",
    "series.signup_reminder",
    "tournament.draft_link",
    "tournament.herodraft_link",
    "lobby.info",
}


def _clean_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k != "DJANGO_SETTINGS_MODULE"}
    return env


class RegistryImportTest(TestCase):
    def test_imports_without_django(self) -> None:
        code = (
            "import sys\n"
            "sys.path.insert(0, sys.argv[1])\n"
            "import notifications.registry as r\n"
            "assert r.MESSAGE_TYPES\n"
            "print(sorted(m for m in sys.modules if m.split('.')[0] == 'django'))"
        )
        result = subprocess.run(
            [sys.executable, "-I", "-c", code, str(BACKEND_DIR)],
            env=_clean_env(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "[]")


class RegistryInvariantTest(TestCase):
    def test_catalogue_is_valid(self) -> None:
        self.assertEqual(validate_registry(GROUPS, MESSAGE_TYPES), [])

    def test_seeded_keys_present(self) -> None:
        self.assertTrue(SEEDED_KEYS <= {m.key for m in MESSAGE_TYPES})

    def test_keys_unique(self) -> None:
        keys = [m.key for m in MESSAGE_TYPES]
        self.assertEqual(len(keys), len(set(keys)))
        group_keys = [g.key for g in GROUPS]
        self.assertEqual(len(group_keys), len(set(group_keys)))

    def test_message_key_enum_matches_catalogue(self) -> None:
        self.assertEqual([k.value for k in MessageKey], [m.key for m in MESSAGE_TYPES])
        self.assertEqual([k.value for k in GroupKey], [g.key for g in GROUPS])

    def test_every_type_has_required_attributes(self) -> None:
        for m in MESSAGE_TYPES:
            with self.subTest(key=m.key):
                self.assertIsInstance(m.key, MessageKey)
                self.assertRegex(m.key, r"^[a-z][a-z_]*\.[a-z][a-z_]*$")
                self.assertIsInstance(m.group, GroupKey)
                self.assertTrue(m.label.strip())
                self.assertTrue(m.description.strip())
                self.assertIsInstance(m.audience, Audience)
                self.assertTrue(m.channels)
                self.assertTrue(all(isinstance(c, Channel) for c in m.channels))
                self.assertEqual(len(m.channels), len(set(m.channels)))
                self.assertIsInstance(m.essential_default, bool)
                self.assertIsInstance(m.essential_locked, bool)
                self.assertIsInstance(m.urgent, bool)

    def test_every_group_referenced_exists(self) -> None:
        group_keys = {g.key for g in GROUPS}
        for m in MESSAGE_TYPES:
            self.assertIn(m.group, group_keys, m.key)

    def test_locked_implies_essential(self) -> None:
        for m in MESSAGE_TYPES:
            if m.essential_locked:
                self.assertTrue(m.essential_default, m.key)

    def test_conduct_group_is_reserved_locked_essential(self) -> None:
        conduct = get_group(CONDUCT_GROUP)
        self.assertTrue(conduct.essential_locked)
        self.assertFalse(conduct.opt_outable_default)
        for m in types_in_group(CONDUCT_GROUP):
            self.assertTrue(m.essential_locked, m.key)
            self.assertTrue(m.essential_default, m.key)

    def test_channel_post_only_types_never_opt_outable(self) -> None:
        for m in MESSAGE_TYPES:
            if set(m.channels) == {Channel.CHANNEL_POST}:
                self.assertFalse(get_group(m.group).opt_outable_default, m.key)

    def test_reference_defaults(self) -> None:
        opt_outable = {g.key for g in GROUPS if g.opt_outable_default}
        self.assertEqual(
            opt_outable, {"roster_changes", "pre_game_reminders", "series_updates"}
        )
        essential = {m.key for m in MESSAGE_TYPES if m.essential_default}
        self.assertEqual(
            essential,
            {
                "rsvp.confirm_request",
                "rsvp.reachability_check",
                "rsvp.escalation_nudge",
                "rsvp.promotion",
            },
        )
        self.assertTrue(get_message_type("rsvp.promotion").urgent)
        self.assertTrue(get_message_type("rsvp.escalation_nudge").urgent)


class ValidateRegistryTest(TestCase):
    def _type(self, **overrides: object) -> MessageType:
        return replace(get_message_type(MessageKey.RSVP_ROSTER_CHANGE), **overrides)

    def test_duplicate_key(self) -> None:
        errors = validate_registry(GROUPS, (*MESSAGE_TYPES, MESSAGE_TYPES[0]))
        self.assertTrue(any("duplicate message key" in e for e in errors), errors)

    def test_unknown_group(self) -> None:
        errors = validate_registry(GROUPS, (self._type(group="nope"),))
        self.assertTrue(any("unknown group" in e for e in errors), errors)

    def test_locked_without_essential(self) -> None:
        bad = self._type(essential_locked=True, essential_default=False)
        errors = validate_registry(GROUPS, (bad,))
        self.assertTrue(any("essential_locked" in e for e in errors), errors)

    def test_unlocked_type_in_conduct(self) -> None:
        bad = self._type(group=GroupKey.CONDUCT, essential_default=True)
        errors = validate_registry(GROUPS, (bad,))
        self.assertTrue(any("conduct" in e for e in errors), errors)

    def test_channel_post_only_in_opt_outable_group(self) -> None:
        bad = self._type(channels=(Channel.CHANNEL_POST,))
        errors = validate_registry(GROUPS, (bad,))
        self.assertTrue(any("channel_post" in e for e in errors), errors)

    def test_empty_fields(self) -> None:
        bad = self._type(label=" ", description="", channels=())
        errors = validate_registry(GROUPS, (bad,))
        for word in ("label", "description", "channels"):
            self.assertTrue(any(word in e for e in errors), (word, errors))

    def test_bad_key_format(self) -> None:
        errors = validate_registry(GROUPS, (self._type(key="Bad-Key"),))
        self.assertTrue(any("key format" in e for e in errors), errors)

    def test_locked_group_must_not_be_opt_outable(self) -> None:
        groups = tuple(
            replace(g, opt_outable_default=True) if g.key == CONDUCT_GROUP else g
            for g in GROUPS
        )
        errors = validate_registry(groups, MESSAGE_TYPES)
        self.assertTrue(any("conduct" in e for e in errors), errors)


class GetMessageTypeTest(TestCase):
    def test_lookup_by_enum_and_string(self) -> None:
        by_enum = get_message_type(MessageKey.RSVP_PROMOTION)
        self.assertIs(by_enum, get_message_type("rsvp.promotion"))
        self.assertEqual(by_enum.key, "rsvp.promotion")
        self.assertEqual(by_enum.group, GroupKey.ROSTER_CHANGES)

    def test_unknown_key_raises(self) -> None:
        with self.assertRaises(KeyError):
            get_message_type("rsvp.nope")

    def test_get_group(self) -> None:
        self.assertIsInstance(get_group("roster_changes"), MessageGroup)
        with self.assertRaises(KeyError):
            get_group("nope")

    def test_types_in_group_preserves_order(self) -> None:
        roster = types_in_group(GroupKey.ROSTER_CHANGES)
        expected = tuple(m for m in MESSAGE_TYPES if m.group == "roster_changes")
        self.assertEqual(roster, expected)
        self.assertIn(get_message_type("rsvp.promotion"), roster)


class ExporterTest(TestCase):
    def _run_main(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = export_schema.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_render_is_deterministic(self) -> None:
        self.assertEqual(export_schema.render(), export_schema.render())

    def test_render_contents(self) -> None:
        text = export_schema.render()
        self.assertTrue(text.startswith("// GENERATED FILE"))
        self.assertTrue(text.endswith("\n"))
        self.assertNotIn("\n\n\n", text)
        self.assertIn("import { z } from 'zod';", text)
        for name in (
            "MessageKeySchema",
            "MessageGroupKeySchema",
            "MessageGroupSchema",
            "MessageTypeSchema",
            "MESSAGE_KEYS",
            "MESSAGE_GROUPS",
            "MESSAGE_TYPES",
        ):
            self.assertRegex(text, rf"export const {name}\b")
        for m in MESSAGE_TYPES:
            self.assertIn(f"'{m.key}'", text)
        for line in text.splitlines():
            self.assertEqual(line, line.rstrip(), "trailing whitespace")

    def test_string_quoting_follows_prettier(self) -> None:
        self.assertEqual(export_schema.ts_string("plain"), "'plain'")
        self.assertEqual(export_schema.ts_string("it's"), '"it\'s"')
        self.assertEqual(export_schema.ts_string('a "b" c\'s'), "'a \"b\" c\\'s'")
        self.assertEqual(export_schema.ts_string("back\\slash"), "'back\\\\slash'")

    def test_long_values_break_like_prettier(self) -> None:
        long = "x" * 80
        text = export_schema.object_literal((("key", long), ("label", long)))
        self.assertIn(f"    key: '{long}',\n", text)
        self.assertIn(f"    label:\n      '{long}',\n", text)
        fits = "x" * (80 - len("    label: '',"))
        text = export_schema.object_literal((("label", fits),))
        self.assertIn(f"    label: '{fits}',\n", text)

    def test_write_then_check_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "nested" / "messageTypes.generated.ts"
            code, _, _ = self._run_main("--out", str(out))
            self.assertEqual(code, 0)
            self.assertEqual(out.read_text(encoding="utf-8"), export_schema.render())
            first = out.read_bytes()
            self._run_main("--out", str(out))
            self.assertEqual(out.read_bytes(), first)
            code, _, err = self._run_main("--out", str(out), "--check")
            self.assertEqual(code, 0, err)

    def test_check_fails_with_diff_when_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "messageTypes.generated.ts"
            out.write_text(
                export_schema.render().replace("'lobby.info'", "'lobby.old'"),
                encoding="utf-8",
            )
            before = out.read_bytes()
            code, stdout, stderr = self._run_main("--out", str(out), "--check")
            self.assertEqual(code, 1)
            self.assertIn("-  'lobby.old'", stdout + stderr)
            self.assertIn("+  'lobby.info'", stdout + stderr)
            self.assertIn("just py::gen-message-types", stdout + stderr)
            self.assertEqual(out.read_bytes(), before)

    def test_check_fails_when_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "missing.ts"
            code, _, _ = self._run_main("--out", str(out), "--check")
            self.assertEqual(code, 1)
            self.assertFalse(out.exists())

    def test_default_out_path(self) -> None:
        self.assertEqual(
            export_schema.DEFAULT_OUT.relative_to(BACKEND_DIR.parent).as_posix(),
            "frontend/app/lib/notifications/messageTypes.generated.ts",
        )

    def test_script_runs_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "gen.ts"
            args = [sys.executable, "-I", str(SCRIPT), "--out", str(out)]
            kwargs = dict(env=_clean_env(), capture_output=True, text=True, timeout=60)
            first = subprocess.run(args, cwd=tmp, **kwargs)
            self.assertEqual(first.returncode, 0, first.stderr)
            self.assertEqual(out.read_text(encoding="utf-8"), export_schema.render())
            ok = subprocess.run([*args, "--check"], cwd=tmp, **kwargs)
            self.assertEqual(ok.returncode, 0, ok.stderr)
            out.write_text("stale\n", encoding="utf-8")
            stale = subprocess.run([*args, "--check"], cwd=tmp, **kwargs)
            self.assertEqual(stale.returncode, 1)
            self.assertTrue(re.search(r"^\+// GENERATED FILE", stale.stdout, re.M))
