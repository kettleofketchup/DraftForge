"""Operator bindings from DraftForge orgs and events to the external guild.

``PROMOTION_SYNC_BINDINGS`` is the only source of guild and occasion IDs: a
request can never supply them, nothing is inferred from names or dates, and
any ambiguity fails at startup instead of picking one mapping.
"""

import json
from datetime import timedelta

from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings
from django.utils import timezone as tz

from config.promotion_sync import PromotionSyncConfig
from events.models import Event
from events.tests.base import EventTestCase
from org.integration.bindings import EventBinding, get_event_binding
from org.integration.errors import IntegrationError
from org.models import Organization

GUILD = "555000000000000001"


def _env(value) -> dict[str, str]:
    raw = value if isinstance(value, str) else json.dumps(value)
    return {"PROMOTION_SYNC_BINDINGS": raw}


def _binding(org="41", guild=GUILD, events=(("720", "88"),)) -> dict:
    return {
        "org_id": org,
        "guild_id": guild,
        "events": [{"event_id": e, "occasion_id": o} for e, o in events],
    }


class ConfigParsingTests(SimpleTestCase):
    def test_unset_or_blank_is_empty(self) -> None:
        for env in ({}, _env(""), _env("   ")):
            with self.subTest(env=env):
                config = PromotionSyncConfig.from_env(environ=env)
                self.assertEqual(config.bindings, ())
                self.assertIsNone(config.for_org(41))

    def test_valid_binding_is_normalized_and_immutable(self) -> None:
        config = PromotionSyncConfig.from_env(
            environ=_env([_binding(events=(("720", "88"), ("721", "89")))])
        )
        org = config.for_org(41)
        self.assertEqual(org.guild_id, int(GUILD))
        self.assertEqual(dict(org.events), {720: 88, 721: 89})
        with self.assertRaises(TypeError):
            org.events[722] = 90  # type: ignore[index]
        with self.assertRaises(AttributeError):
            org.guild_id = 1  # type: ignore[misc]

    def test_org_with_no_events_is_allowed(self) -> None:
        config = PromotionSyncConfig.from_env(environ=_env([_binding(events=())]))
        self.assertEqual(dict(config.for_org(41).events), {})

    def test_rejects_malformed_or_ambiguous_configuration(self) -> None:
        cases = {
            "not json": "[{",
            "trailing": json.dumps([_binding()]) + "[]",
            "object top": json.dumps(_binding()),
            "duplicate key": '[{"org_id":"41","org_id":"42","guild_id":"1","events":[]}]',
            "unknown field": [{**_binding(), "name": "Guild"}],
            "unknown event field": [
                {
                    **_binding(),
                    "events": [{"event_id": "1", "occasion_id": "2", "x": 1}],
                }
            ],
            "missing field": [{"org_id": "41", "guild_id": GUILD}],
            "fallback date": [
                {
                    **_binding(),
                    "events": [{"event_id": "1", "occasion_id": None}],
                }
            ],
            "numeric id": [{**_binding(), "org_id": 41}],
            "leading zero": [_binding(org="041")],
            "zero": [_binding(guild="0")],
            "overflow": [_binding(org="9223372036854775808")],
            "duplicate org": [_binding(), _binding(guild="555000000000000002")],
            "guild bound twice": [
                _binding(),
                _binding(org="42", events=(("730", "90"),)),
            ],
            "event twice in org": [_binding(events=(("720", "88"), ("720", "89")))],
            "occasion twice in org": [_binding(events=(("720", "88"), ("721", "88")))],
            "event in two orgs": [
                _binding(),
                _binding(org="42", guild="555000000000000002"),
            ],
        }
        for name, value in cases.items():
            with self.subTest(name), self.assertRaises(ImproperlyConfigured) as ctx:
                PromotionSyncConfig.from_env(environ=_env(value))
            self.assertNotIn(GUILD, str(ctx.exception))

    def test_settings_default_is_empty(self) -> None:
        from django.conf import settings

        self.assertIsInstance(settings.PROMOTION_SYNC, PromotionSyncConfig)


class EventBindingTests(EventTestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.org.discord_server_id = GUILD
        cls.org.save()
        cls.other_org = Organization.objects.create(
            name="Other", discord_server_id="555000000000000002"
        )
        cls.unbound_event = Event.objects.create(
            organization=cls.org,
            name="Unbound",
            scheduled_at=tz.now() + timedelta(days=3),
            created_by=cls.admin,
        )
        cls.foreign_event = Event.objects.create(
            organization=cls.other_org,
            name="Foreign",
            scheduled_at=tz.now() + timedelta(days=3),
            created_by=cls.admin,
        )

    def config(self, *bindings: dict) -> PromotionSyncConfig:
        return PromotionSyncConfig.from_env(environ=_env(list(bindings)))

    def bound(self) -> PromotionSyncConfig:
        return self.config(
            _binding(
                org=str(self.org.pk),
                events=((str(self.event.pk), "88"), (str(self.foreign_event.pk), "89")),
            )
        )

    def assert_error(self, code: str, status: int, org_id: int, event_id: int) -> None:
        with self.assertRaises(IntegrationError) as ctx:
            get_event_binding(org_id, event_id)
        self.assertEqual(
            (ctx.exception.code, ctx.exception.status_code), (code, status)
        )

    def test_returns_explicit_binding(self) -> None:
        with override_settings(PROMOTION_SYNC=self.bound()):
            binding = get_event_binding(self.org.pk, self.event.pk)
        self.assertEqual(
            binding,
            EventBinding(
                org_id=self.org.pk,
                guild_id=int(GUILD),
                event_id=self.event.pk,
                occasion_id=88,
            ),
        )

    def test_missing_org_binding_fails_closed(self) -> None:
        with override_settings(PROMOTION_SYNC=self.config()):
            self.assert_error("binding_missing", 403, self.org.pk, self.event.pk)

    def test_unbound_event_fails_closed(self) -> None:
        with override_settings(PROMOTION_SYNC=self.bound()):
            self.assert_error(
                "binding_missing", 403, self.org.pk, self.unbound_event.pk
            )

    def test_event_of_another_org_is_404_even_if_configured(self) -> None:
        with override_settings(PROMOTION_SYNC=self.bound()):
            self.assert_error("not_found", 404, self.org.pk, self.foreign_event.pk)
            self.assert_error("not_found", 404, self.org.pk, 987654321)

    def test_guild_mismatch_with_org_guild_is_rejected(self) -> None:
        for server_id in ("555000000000000009", None, ""):
            with self.subTest(server_id=server_id):
                Organization.objects.filter(pk=self.org.pk).update(
                    discord_server_id=server_id
                )
                with override_settings(PROMOTION_SYNC=self.bound()):
                    self.assert_error(
                        "binding_mismatch", 403, self.org.pk, self.event.pk
                    )
