"""Message registry invariants and the Zod bundle exporter.

Plain unittest so the module also runs without Django:
`python -m unittest notifications.tests.test_registry` from backend/.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from unittest import TestCase

from pydantic import ValidationError

from notifications import export_schema
from notifications.registry import (
    CONDUCT_GROUP,
    GROUPS,
    MESSAGE_TYPES,
    REGISTRY,
    Audience,
    Channel,
    GroupKey,
    MessageGroup,
    MessageKey,
    MessageRegistry,
    MessageType,
    get_group,
    get_message_type,
    registry_errors,
    types_in_group,
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
        self.assertEqual(registry_errors(GROUPS, MESSAGE_TYPES), [])

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


def _entry(**overrides: object) -> dict[str, object]:
    base = get_message_type(MessageKey.RSVP_ROSTER_CHANGE).model_dump()
    return {**base, **overrides}


def _type(**overrides: object) -> MessageType:
    return MessageType(**_entry(**overrides))


class EntryValidationTest(TestCase):
    def test_locked_without_essential(self) -> None:
        with self.assertRaisesRegex(ValidationError, "essential_locked"):
            _type(essential_locked=True, essential_default=False)

    def test_blank_or_empty_fields(self) -> None:
        for field, value in (("label", " "), ("description", ""), ("channels", ())):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                _type(**{field: value})

    def test_duplicate_channels(self) -> None:
        with self.assertRaisesRegex(ValidationError, "duplicate channels"):
            _type(channels=(Channel.DM, Channel.DM))

    def test_unknown_enum_values(self) -> None:
        for field in ("key", "group", "audience"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                _type(**{field: "nope"})

    def test_unknown_field_rejected(self) -> None:
        with self.assertRaises(ValidationError):
            _type(surprise=True)

    def test_frozen(self) -> None:
        with self.assertRaises(ValidationError):
            get_message_type(MessageKey.RSVP_PROMOTION).urgent = False  # type: ignore[misc]

    def test_locked_group_must_not_be_opt_outable(self) -> None:
        conduct = get_group(CONDUCT_GROUP).model_dump()
        with self.assertRaisesRegex(ValidationError, "opt-outable"):
            MessageGroup(**{**conduct, "opt_outable_default": True})

    def test_camel_case_round_trip(self) -> None:
        for m in MESSAGE_TYPES:
            with self.subTest(key=m.key):
                dumped = m.model_dump(mode="json", by_alias=True)
                self.assertIn("essentialDefault", dumped)
                self.assertEqual(MessageType.model_validate(dumped), m)


class RegistryErrorsTest(TestCase):
    def test_duplicate_key(self) -> None:
        errors = registry_errors(GROUPS, (*MESSAGE_TYPES, MESSAGE_TYPES[0]))
        self.assertTrue(any("duplicate message key" in e for e in errors), errors)

    def test_unknown_group(self) -> None:
        groups = tuple(g for g in GROUPS if g.key != GroupKey.ROSTER_CHANGES)
        errors = registry_errors(groups, (_type(),))
        self.assertTrue(any("unknown group" in e for e in errors), errors)

    def test_missing_conduct_group(self) -> None:
        groups = tuple(g for g in GROUPS if g.key != CONDUCT_GROUP)
        errors = registry_errors(groups, ())
        self.assertTrue(any("missing reserved group" in e for e in errors), errors)

    def test_unlocked_type_in_conduct(self) -> None:
        bad = _type(group=GroupKey.CONDUCT, essential_default=True)
        errors = registry_errors(GROUPS, (bad,))
        self.assertTrue(any("conduct" in e for e in errors), errors)

    def test_channel_post_only_in_opt_outable_group(self) -> None:
        bad = _type(channels=(Channel.CHANNEL_POST,))
        errors = registry_errors(GROUPS, (bad,))
        self.assertTrue(any("channel_post" in e for e in errors), errors)

    def test_bad_key_format(self) -> None:
        bad = MessageType.model_construct(**_entry(key="Bad-Key"))
        errors = registry_errors(GROUPS, (bad,))
        self.assertTrue(any("key format" in e for e in errors), errors)

    def test_registry_model_runs_the_checks(self) -> None:
        with self.assertRaisesRegex(ValidationError, "duplicate message key"):
            MessageRegistry(
                groups=GROUPS, message_types=(*MESSAGE_TYPES, MESSAGE_TYPES[0])
            )


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
    def test_bundle_is_deterministic(self) -> None:
        self.assertEqual(export_schema.bundle(), export_schema.bundle())

    def test_bundle_shape(self) -> None:
        b = export_schema.bundle()
        self.assertEqual(b["version"], 1)
        self.assertEqual(b["source"], "backend/notifications/registry.py")
        self.assertEqual(b["regen"], "just py::gen-message-types")
        self.assertEqual(b["schema"]["title"], "MessageRegistry")
        self.assertLessEqual(
            {"MessageGroup", "MessageType", "MessageKey", "GroupKey"},
            set(b["schema"]["$defs"]),
        )
        self.assertEqual(b["data"]["name"], "MESSAGE_REGISTRY")
        self.assertEqual(b["data"]["type"], "MessageRegistry")
        value = b["data"]["value"]
        self.assertEqual(MessageRegistry.model_validate(value), REGISTRY)

    def test_every_field_required_and_strict(self) -> None:
        defs = export_schema.bundle()["schema"]["$defs"]
        for name in ("MessageGroup", "MessageType"):
            with self.subTest(model=name):
                schema = defs[name]
                self.assertEqual(set(schema["required"]), set(schema["properties"]))
                self.assertIs(schema["additionalProperties"], False)

    def test_constraints_reach_the_schema(self) -> None:
        props = export_schema.bundle()["schema"]["$defs"]["MessageType"]["properties"]
        self.assertEqual(props["label"]["minLength"], 1)
        self.assertEqual(props["label"]["pattern"], r"\S")
        self.assertEqual(props["channels"]["minItems"], 1)

    def test_script_runs_isolated(self) -> None:
        result = subprocess.run(
            [sys.executable, "-I", str(SCRIPT)],
            env=_clean_env(),
            capture_output=True,
            text=True,
            timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), export_schema.bundle())
