from datetime import datetime, timedelta
from typing import Any
from unittest.mock import patch

from django.utils import timezone

from app.models import CustomUser
from events.constants import SignupStatus
from events.models import Event, EventSignup
from org.promotion.recipients import (
    CandidateSource,
    candidates,
    clamp_days,
    in_pool,
)
from org.tests.test_promotion_api import PromotionApiBase
from tournament.models import Tournament

GUILD_ID = "770000000000000001"
FETCH = "org.promotion.recipients.get_discord_members_data"


def guild_member(
    discord_id: str,
    username: str,
    *,
    joined: datetime,
    nick: str | None = None,
    bot: bool = False,
) -> dict[str, Any]:
    return {
        "user": {
            "id": discord_id,
            "username": username,
            "global_name": f"{username} Global",
            "avatar": None,
            **({"bot": True} if bot else {}),
        },
        "nick": nick,
        "joined_at": joined.isoformat(),
    }


class ClampDaysTest(PromotionApiBase):
    def test_clamps(self) -> None:
        self.assertEqual(clamp_days(None), 30)
        self.assertEqual(clamp_days("x"), 30)
        self.assertEqual(clamp_days("500"), 90)
        self.assertEqual(clamp_days("0"), 1)
        self.assertEqual(clamp_days("14"), 14)


class _SourcesBase(PromotionApiBase):
    def setUp(self) -> None:
        super().setUp()
        self.now = timezone.now()
        self.org.discord_server_id = GUILD_ID
        self.org.save()
        self.sender = self.users["promoter"]
        assert self.sender is not None

    def _signup(self, user: CustomUser, event: Event, *, days_ago: float) -> None:
        signup = EventSignup.objects.create(event=event, user=user)
        EventSignup.objects.filter(pk=signup.pk).update(
            signed_up_at=self.now - timedelta(days=days_ago)
        )

    def _rows(self, source: CandidateSource, **kwargs: Any) -> list[dict[str, Any]]:
        return list(
            candidates(
                self.org,
                self.event,
                n=3,
                sender=self.sender,
                source=source,
                **kwargs,
            )
        )


class ActiveSourceTest(_SourcesBase):
    def test_lists_recent_signups_and_players_newest_first(self) -> None:
        signer = self._user("src_signer")
        self._signup(signer, self.completed_event, days_ago=2)
        stale = self._user("src_stale")
        self._signup(stale, self.completed_event, days_ago=60)

        rows = self._rows(CandidateSource.ACTIVE, days=30)
        names = [r["username"] for r in rows]
        self.assertEqual(names, ["src_signer", "papi_recipient"])
        self.assertIsNotNone(rows[0]["last_active_at"])
        self.assertIsNone(rows[0]["recent_count"])

        names_90 = [r["username"] for r in self._rows(CandidateSource.ACTIVE, days=90)]
        self.assertIn("src_stale", names_90)

    def test_ignores_other_orgs_and_this_event(self) -> None:
        other = self._user("src_other_org")
        self._signup(other, self.other_event, days_ago=1)
        this_event = self._user("src_this_event")
        self._signup(this_event, self.event, days_ago=1)

        names = {
            r["username"]
            for r in self._rows(CandidateSource.ACTIVE, hide_signed_up=False)
        }
        self.assertNotIn("src_other_org", names)
        self.assertNotIn("src_this_event", names)

    def test_excludes_sender_and_declined(self) -> None:
        self._signup(self.sender, self.completed_event, days_ago=1)
        declined = self._user("src_declined")
        self._signup(declined, self.completed_event, days_ago=1)
        EventSignup.objects.create(
            event=self.event, user=declined, status=SignupStatus.REJECTED
        )
        names = {r["username"] for r in self._rows(CandidateSource.ACTIVE)}
        self.assertNotIn(self.sender.username, names)
        self.assertNotIn("src_declined", names)

    def test_tournament_outside_window_not_active(self) -> None:
        old = self._user("src_old_player")
        t = Tournament.objects.create(
            name="Old",
            date_played=self.now - timedelta(days=45),
            league=self.league,
        )
        t.users.add(old)
        self.assertNotIn(
            "src_old_player",
            {r["username"] for r in self._rows(CandidateSource.ACTIVE, days=30)},
        )


class DiscordSourceTest(_SourcesBase):
    def _members(self) -> list[dict[str, Any]]:
        linked = self._user("src_linked")
        self.linked = linked
        return [
            guild_member("990001", "fresh", joined=self.now - timedelta(days=1)),
            guild_member(
                linked.discordId or "",
                "src_linked_dc",
                joined=self.now - timedelta(days=3),
            ),
            guild_member("990002", "oldtimer", joined=self.now - timedelta(days=200)),
            guild_member("990003", "botty", joined=self.now, bot=True),
            guild_member(
                self.sender.discordId or "", "me", joined=self.now - timedelta(hours=1)
            ),
        ]

    def test_newest_first_with_and_without_accounts(self) -> None:
        with patch(FETCH, return_value=self._members()):
            rows = self._rows(CandidateSource.DISCORD, days=30)
        self.assertEqual([r["discordId"] for r in rows][:1], ["990001"])
        self.assertEqual(len(rows), 2)
        fresh, linked = rows
        self.assertIsNone(fresh["user_pk"])
        self.assertEqual(fresh["discordUsername"], "fresh")
        self.assertIsNotNone(fresh["discord_joined_at"])
        self.assertEqual(linked["user_pk"], self.linked.pk)

    def test_search_filters_unlinked_members(self) -> None:
        with patch(FETCH, return_value=self._members()):
            rows = self._rows(CandidateSource.DISCORD, q="FRESH")
        self.assertEqual([r["discordId"] for r in rows], ["990001"])

    def test_no_guild_means_empty(self) -> None:
        self.org.discord_server_id = None
        self.org.save()
        self.assertEqual(self._rows(CandidateSource.DISCORD), [])


class InPoolUnionTest(_SourcesBase):
    def test_active_member_is_in_pool(self) -> None:
        active = self._user("src_pool_active")
        self.assertFalse(in_pool(self.org, self.event, active))
        self._signup(active, self.completed_event, days_ago=5)
        self.assertTrue(in_pool(self.org, self.event, active))

    def test_recent_guild_joiner_is_in_pool(self) -> None:
        joiner = self._user("src_pool_joiner")
        members = [
            guild_member(
                joiner.discordId or "", "j", joined=self.now - timedelta(days=2)
            )
        ]
        with patch(FETCH, return_value=members):
            self.assertTrue(in_pool(self.org, self.event, joiner))
        with patch(FETCH, return_value=[]):
            self.assertFalse(in_pool(self.org, self.event, joiner))


class SourcesApiTest(_SourcesBase):
    def _member_url(self) -> str:
        return f"{self.candidates_url()}discord/"

    def test_candidates_accepts_source_and_days(self) -> None:
        response = self.request(
            "promoter", "get", self.candidates_url(), {"source": "active", "days": 7}
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual((body["source"], body["days"]), ("active", 7))
        self.assertEqual([r["username"] for r in body["rows"]], ["papi_recipient"])

    def test_bad_source_400(self) -> None:
        response = self.request(
            "promoter", "get", self.candidates_url(), {"source": "everyone"}
        )
        self.assertEqual(response.status_code, 400)

    def test_resolve_creates_account_then_render_and_send_work(self) -> None:
        members = [guild_member("990777", "newbie", joined=self.now, nick="Newb")]
        with patch(FETCH, return_value=members):
            response = self.request(
                "promoter", "post", self._member_url(), {"discord_id": "990777"}
            )
            self.assertEqual(response.status_code, 200, response.content)
            row = response.json()
            user = CustomUser.objects.get(discordId="990777")
            self.assertEqual(row["user_pk"], user.pk)
            self.assertEqual(user.discordUsername, "newbie")

            again = self.request(
                "promoter", "post", self._member_url(), {"discord_id": "990777"}
            )
            self.assertEqual(again.json()["user_pk"], user.pk)
            self.assertEqual(CustomUser.objects.filter(discordId="990777").count(), 1)

            sent = self.request(
                "promoter",
                "post",
                self.sends_url(),
                {"template_id": None, "recipient_id": user.pk, "text": "Hi"},
            )
            self.assertEqual(sent.status_code, 201, sent.content)

    def test_resolve_rejects_non_member(self) -> None:
        with patch(FETCH, return_value=[]):
            response = self.request(
                "promoter", "post", self._member_url(), {"discord_id": "990778"}
            )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(CustomUser.objects.filter(discordId="990778").exists())

    def test_resolve_needs_promoter(self) -> None:
        response = self.request(
            "member", "post", self._member_url(), {"discord_id": "990779"}
        )
        self.assertEqual(response.status_code, 403)
