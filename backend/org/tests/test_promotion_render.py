import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict

from django.test import SimpleTestCase, TestCase, override_settings

from app.models import CustomUser, League, Organization
from events.models import Event
from org.promotion.render import (
    ANY_TOKEN_RE,
    PLACEHOLDERS,
    TOKEN_RE,
    build_context,
    player_name,
    render_template,
    validate_template_body,
)
from org.promotion.starter import STARTER_TEMPLATE_BODY

FIXTURE_PATH = Path(__file__).parent / "render_fixture.json"

EXPECTED_KEYS = [
    "player",
    "promoter",
    "event",
    "event_time",
    "event_time_relative",
    "event_date",
    "signups_open",
    "event_link",
    "org",
    "discord_link",
]


class FixtureCase(TypedDict):
    name: str
    body: str
    text: str
    warnings: list[str]


class Fixture(TypedDict):
    context: dict[str, str]
    cases: list[FixtureCase]


def load_fixture() -> Fixture:
    with FIXTURE_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


class RenderFixtureTest(SimpleTestCase):
    def test_fixture_context_has_every_placeholder(self) -> None:
        fixture = load_fixture()
        self.assertEqual(list(fixture["context"]), EXPECTED_KEYS)

    def test_fixture_cases(self) -> None:
        fixture = load_fixture()
        self.assertGreater(len(fixture["cases"]), 0)
        for case in fixture["cases"]:
            with self.subTest(case=case["name"]):
                result = render_template(case["body"], fixture["context"])
                self.assertEqual(result.text, case["text"])
                self.assertEqual(result.warnings, case["warnings"])

    def test_fixture_covers_required_edge_cases(self) -> None:
        names = {case["name"] for case in load_fixture()["cases"]}
        for required in (
            "basic",
            "format_spec",
            "attribute",
            "stray_open",
            "double_brace",
            "unknown",
            "repeat",
            "empty_signups",
        ):
            self.assertIn(required, names)


class PlaceholderSpecTest(SimpleTestCase):
    def test_placeholders_in_spec_order(self) -> None:
        self.assertEqual([p["key"] for p in PLACEHOLDERS], EXPECTED_KEYS)
        for spec in PLACEHOLDERS:
            self.assertTrue(spec["description"])

    def test_token_re_matches_exactly_the_whitelist(self) -> None:
        for key in EXPECTED_KEYS:
            self.assertIsNotNone(TOKEN_RE.fullmatch("{" + key + "}"))
        self.assertIsNone(TOKEN_RE.fullmatch("{player:>9}"))
        self.assertIsNotNone(ANY_TOKEN_RE.fullmatch("{player:>9}"))


class ValidateTemplateBodyTest(SimpleTestCase):
    def test_starter_template_is_clean(self) -> None:
        self.assertEqual(validate_template_body(STARTER_TEMPLATE_BODY), [])

    def test_every_whitelisted_token_is_clean(self) -> None:
        body = " ".join("{" + key + "}" for key in EXPECTED_KEYS)
        self.assertEqual(validate_template_body(body), [])

    def test_format_spec_gives_one_warning(self) -> None:
        self.assertEqual(
            validate_template_body("{player:>9}"),
            ["unknown placeholder {player:>9}"],
        )

    def test_stray_brace_warns(self) -> None:
        self.assertEqual(validate_template_body("Hi {player"), ["unbalanced brace"])


class PlayerNameTest(TestCase):
    def _user(self, **fields: str | None) -> CustomUser:
        user = CustomUser.objects.create_user(username="pn_user", password="x")
        for name, value in fields.items():
            setattr(user, name, value)
        user.save()
        return user

    def test_guild_nickname_first(self) -> None:
        user = self._user(
            guildNickname="Guild",
            discordNickname="DiscNick",
            discordUsername="discuser",
            nickname="SiteNick",
        )
        self.assertEqual(player_name(user), "Guild")

    def test_discord_nickname_second(self) -> None:
        user = self._user(
            discordNickname="DiscNick", discordUsername="discuser", nickname="Site"
        )
        self.assertEqual(player_name(user), "DiscNick")

    def test_discord_username_third(self) -> None:
        user = self._user(discordUsername="discuser", nickname="Site")
        self.assertEqual(player_name(user), "discuser")

    def test_site_nickname_fourth(self) -> None:
        user = self._user(nickname="Site")
        self.assertEqual(player_name(user), "Site")

    def test_username_last(self) -> None:
        user = self._user()
        self.assertEqual(player_name(user), "pn_user")

    def test_blank_values_are_skipped(self) -> None:
        user = self._user(guildNickname="", discordNickname="", discordUsername="d")
        self.assertEqual(player_name(user), "d")


@override_settings(SITE_URL="https://dota.example")
class BuildContextTest(TestCase):
    def setUp(self) -> None:
        self.admin = CustomUser.objects.create_user(username="bc_admin", password="x")
        self.sender = CustomUser.objects.create_user(username="bc_sender", password="x")
        self.sender.discordUsername = "sender_disc"
        self.sender.save()
        self.recipient = CustomUser.objects.create_user(
            username="bc_recipient", password="x"
        )
        self.recipient.guildNickname = "Ann"
        self.recipient.save()
        self.org = Organization.objects.create(
            name="Render Org",
            owner=self.admin,
            discord_link="https://discord.gg/render",
        )
        self.league = League.objects.create(
            name="Render League", organization=self.org, steam_league_id=99781
        )
        self.event = Event.objects.create(
            organization=self.org,
            name="Render Event",
            scheduled_at=datetime(2026, 11, 15, 1, 0, tzinfo=UTC),
            signups_open_at=datetime(2026, 11, 14, 1, 0, tzinfo=UTC),
            created_by=self.admin,
            tournament_league=self.league,
        )

    def _context(self) -> dict[str, str]:
        return build_context(
            event=self.event,
            recipient=self.recipient,
            sender=self.sender,
            org=self.org,
        )

    def test_keys_match_placeholders(self) -> None:
        self.assertEqual(set(self._context()), {p["key"] for p in PLACEHOLDERS})

    def test_values(self) -> None:
        self.assertEqual(
            self._context(),
            {
                "player": "Ann",
                "promoter": "sender_disc",
                "event": "Render Event",
                "event_time": "<t:1794704400:F>",
                "event_time_relative": "<t:1794704400:R>",
                "event_date": "<t:1794704400:D>",
                "signups_open": "<t:1794618000:R>",
                "event_link": f"https://dota.example/events/{self.event.pk}",
                "org": "Render Org",
                "discord_link": "https://discord.gg/render",
            },
        )

    def test_missing_signups_open_and_discord_link_are_empty(self) -> None:
        self.event.signups_open_at = None
        self.org.discord_link = ""
        context = self._context()
        self.assertEqual(context["signups_open"], "")
        self.assertEqual(context["discord_link"], "")

    def test_rendered_with_starter_template(self) -> None:
        result = render_template(STARTER_TEMPLATE_BODY, self._context())
        self.assertEqual(result.warnings, [])
        self.assertIn("Hey Ann!", result.text)
        self.assertIn("<t:1794704400:F>", result.text)
        self.assertNotIn("{", result.text)
