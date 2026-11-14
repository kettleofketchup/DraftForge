from datetime import timedelta

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from app.models import CustomUser, League, Organization, Tournament
from events.constants import EventState, SignupStatus
from events.models import Event, EventSignup
from org.models import PromoSend
from org.promotion.recipients import (
    DEFAULT_POOL_N,
    MAX_POOL_N,
    candidate_pool,
    candidates,
    clamp_pool_n,
    in_pool,
    recent_org_tournaments,
)


class ClampPoolNTest(SimpleTestCase):
    def test_clamps_above_max(self) -> None:
        self.assertEqual(clamp_pool_n("50"), MAX_POOL_N)
        self.assertEqual(clamp_pool_n("50"), 10)

    def test_invalid_falls_back_to_default(self) -> None:
        self.assertEqual(clamp_pool_n("x"), DEFAULT_POOL_N)
        self.assertEqual(clamp_pool_n("x"), 3)
        self.assertEqual(clamp_pool_n(None), 3)
        self.assertEqual(clamp_pool_n(""), 3)

    def test_clamps_below_min(self) -> None:
        self.assertEqual(clamp_pool_n(0), 1)
        self.assertEqual(clamp_pool_n("-4"), 1)

    def test_passes_valid_values(self) -> None:
        self.assertEqual(clamp_pool_n(7), 7)
        self.assertEqual(clamp_pool_n("5"), 5)


class _PoolFixture(TestCase):
    def setUp(self) -> None:
        self.now = timezone.now()
        self.owner = CustomUser.objects.create_user(username="pool_owner", password="x")
        self.sender = self._user("pool_sender")
        self.org = Organization.objects.create(name="Pool Org", owner=self.owner)
        self.other_org = Organization.objects.create(
            name="Other Pool Org", owner=self.owner
        )
        self.league = League.objects.create(
            name="Pool League", organization=self.org, steam_league_id=88101
        )
        self.other_league = League.objects.create(
            name="Other Pool League", organization=self.other_org, steam_league_id=88102
        )
        self.event = Event.objects.create(
            organization=self.org,
            name="Promoted Event",
            scheduled_at=self.now + timedelta(days=3),
            created_by=self.owner,
        )
        self._seq = 0

    def _user(self, username: str, *, discord: bool = True) -> CustomUser:
        user = CustomUser.objects.create_user(username=username, password="x")
        if discord:
            user.discordId = str(880000000000000000 + user.pk)
            user.discordUsername = f"{username}_dc"
            user.save()
        return user

    def _tournament(
        self,
        players: list[CustomUser],
        *,
        days_ago: float,
        league: League | None = None,
    ) -> Tournament:
        self._seq += 1
        tournament = Tournament.objects.create(
            name=f"Pool T{self._seq}",
            date_played=self.now - timedelta(days=days_ago),
            league=league,
        )
        tournament.users.add(*players)
        return tournament

    def _event_tournament(
        self,
        players: list[CustomUser],
        *,
        days_ago: float,
        state: str = EventState.COMPLETED,
        org: Organization | None = None,
    ) -> Tournament:
        tournament = self._tournament(players, days_ago=days_ago)
        Event.objects.create(
            organization=org or self.org,
            name=f"Source {tournament.name}",
            scheduled_at=tournament.date_played,
            created_by=self.owner,
            state=state,
            tournament=tournament,
        )
        return tournament

    def _pool_usernames(self, n: int) -> set[str]:
        return set(
            candidate_pool(self.org, self.event, n=n, sender=self.sender).values_list(
                "username", flat=True
            )
        )


class RecentOrgTournamentsTest(_PoolFixture):
    def test_upcoming_series_tournaments_ignored(self) -> None:
        past_players = [self._user(f"past_{i}") for i in range(3)]
        future_player = self._user("future_signup")
        for i in range(3):
            self._event_tournament(
                [future_player],
                days_ago=-(i + 1) * 7,
                state=EventState.UPCOMING,
            )
        past = [
            self._tournament([p], days_ago=10 + i, league=self.league)
            for i, p in enumerate(past_players)
        ]

        ids = recent_org_tournaments(self.org, exclude_event=self.event, n=3)

        self.assertEqual(ids, [t.pk for t in past])
        self.assertEqual(self._pool_usernames(3), {p.username for p in past_players})

    def test_cancelled_source_event_excluded(self) -> None:
        cancelled_player = self._user("cancelled_player")
        kept_player = self._user("kept_player")
        cancelled = self._event_tournament(
            [cancelled_player], days_ago=1, state=EventState.CANCELLED
        )
        kept = self._tournament([kept_player], days_ago=2, league=self.league)

        ids = recent_org_tournaments(self.org, exclude_event=self.event, n=3)

        self.assertNotIn(cancelled.pk, ids)
        self.assertIn(kept.pk, ids)
        self.assertEqual(self._pool_usernames(3), {"kept_player"})

    def test_leagueless_event_tournament_counted_via_source_event(self) -> None:
        player = self._user("leagueless_player")
        tournament = self._event_tournament([player], days_ago=1)

        ids = recent_org_tournaments(self.org, exclude_event=self.event, n=3)

        self.assertEqual(ids, [tournament.pk])
        self.assertEqual(self._pool_usernames(3), {"leagueless_player"})

    def test_promoted_event_own_tournament_excluded(self) -> None:
        player = self._user("own_tournament_player")
        own = self._tournament([player], days_ago=1, league=self.league)
        self.event.tournament = own
        self.event.save()

        ids = recent_org_tournaments(self.org, exclude_event=self.event, n=3)

        self.assertNotIn(own.pk, ids)

    def test_other_org_tournaments_ignored(self) -> None:
        player = self._user("other_org_player")
        self._tournament([player], days_ago=1, league=self.other_league)
        self._event_tournament([player], days_ago=2, org=self.other_org)

        self.assertEqual(
            recent_org_tournaments(self.org, exclude_event=self.event, n=3), []
        )


class CandidatePoolTest(_PoolFixture):
    def test_user_without_discord_hidden(self) -> None:
        no_discord = self._user("no_discord", discord=False)
        empty_discord = self._user("empty_discord", discord=False)
        empty_discord.discordId = ""
        empty_discord.save()
        linked = self._user("linked")
        self._tournament(
            [no_discord, empty_discord, linked], days_ago=1, league=self.league
        )

        self.assertEqual(self._pool_usernames(3), {"linked"})

    def test_sender_hidden(self) -> None:
        player = self._user("pool_player")
        self._tournament([self.sender, player], days_ago=1, league=self.league)

        self.assertEqual(self._pool_usernames(3), {"pool_player"})

    def test_recent_count_counts_tournaments_in_window(self) -> None:
        regular = self._user("regular")
        once = self._user("once")
        self._tournament([regular, once], days_ago=1, league=self.league)
        self._tournament([regular], days_ago=2, league=self.league)
        self._tournament([regular], days_ago=3, league=self.league)
        self._tournament([regular], days_ago=4, league=self.league)

        counts = dict(
            candidate_pool(self.org, self.event, n=3, sender=self.sender).values_list(
                "username", "recent_count"
            )
        )

        self.assertEqual(counts, {"regular": 3, "once": 1})

    def test_in_pool_true_for_seventh_most_recent_tournament_player(self) -> None:
        seventh = self._user("seventh")
        for i in range(10):
            players = [seventh] if i == 6 else [self._user(f"filler_{i}")]
            self._tournament(players, days_ago=i + 1, league=self.league)

        self.assertNotIn("seventh", self._pool_usernames(3))
        self.assertTrue(in_pool(self.org, self.event, seventh))

    def test_in_pool_false_beyond_max_n(self) -> None:
        eleventh = self._user("eleventh")
        for i in range(11):
            players = [eleventh] if i == 10 else [self._user(f"filler_{i}")]
            self._tournament(players, days_ago=i + 1, league=self.league)

        self.assertFalse(in_pool(self.org, self.event, eleventh))

    def test_in_pool_false_for_unrelated_user(self) -> None:
        self._tournament([self._user("played")], days_ago=1, league=self.league)

        self.assertFalse(in_pool(self.org, self.event, self._user("stranger")))


class CandidatesTest(_PoolFixture):
    def setUp(self) -> None:
        super().setUp()
        self.ann = self._user("ann")
        self.bob = self._user("bob")
        self._tournament([self.ann, self.bob], days_ago=1, league=self.league)

    def _rows_by_username(self, **kwargs: object) -> dict[str, dict]:
        rows = candidates(self.org, self.event, n=3, sender=self.sender, **kwargs)
        return {row["username"]: row for row in rows}

    def _signup(self, user: CustomUser, status: str) -> EventSignup:
        return EventSignup.objects.create(event=self.event, user=user, status=status)

    def _send(self, recipient: CustomUser, *, sent_at_offset: int) -> PromoSend:
        return PromoSend.objects.create(
            organization=self.org,
            event=self.event,
            recipient=recipient,
            sender=self.sender,
            text="hi",
            sent_at=self.now + timedelta(minutes=sent_at_offset),
        )

    def test_row_shape(self) -> None:
        row = self._rows_by_username()["ann"]

        self.assertEqual(
            set(row),
            {
                "user_pk",
                "username",
                "nickname",
                "discordUsername",
                "discordId",
                "avatarUrl",
                "recent_count",
                "last_messaged",
                "earning_send_exists",
                "signed_up",
            },
        )
        self.assertEqual(row["user_pk"], self.ann.pk)
        self.assertEqual(row["discordUsername"], "ann_dc")
        self.assertEqual(row["discordId"], self.ann.discordId)
        self.assertEqual(row["avatarUrl"], self.ann.avatarUrl)
        self.assertIsNotNone(row["avatarUrl"])
        self.assertEqual(row["recent_count"], 1)
        self.assertIsNone(row["last_messaged"])
        self.assertFalse(row["earning_send_exists"])
        self.assertFalse(row["signed_up"])

    def test_active_signups_hidden_by_default(self) -> None:
        rsvp = self._user("rsvp_player")
        pending = self._user("pending_player")
        waitlisted = self._user("waitlisted_player")
        cancelled = self._user("cancelled_player")
        rejected = self._user("rejected_player")
        self._tournament(
            [rsvp, pending, waitlisted, cancelled, rejected],
            days_ago=2,
            league=self.league,
        )
        self._signup(rsvp, SignupStatus.RSVP)
        self._signup(pending, SignupStatus.PENDING_APPROVAL)
        self._signup(waitlisted, SignupStatus.WAITLISTED)
        self._signup(cancelled, SignupStatus.CANCELLED)
        self._signup(rejected, SignupStatus.REJECTED)

        rows = self._rows_by_username()

        self.assertEqual(
            set(rows), {"ann", "bob", "cancelled_player", "rejected_player"}
        )
        self.assertFalse(rows["cancelled_player"]["signed_up"])
        self.assertFalse(rows["rejected_player"]["signed_up"])

    def test_signed_up_shown_when_filter_off(self) -> None:
        self._signup(self.ann, SignupStatus.RSVP)

        rows = self._rows_by_username(hide_signed_up=False)

        self.assertTrue(rows["ann"]["signed_up"])
        self.assertFalse(rows["bob"]["signed_up"])

    def test_messaged_hidden_by_default(self) -> None:
        self._send(self.ann, sent_at_offset=0)

        self.assertEqual(set(self._rows_by_username()), {"bob"})

    def test_messaged_row_carries_newest_send(self) -> None:
        self._send(self.ann, sent_at_offset=0)
        newest = self._send(self.ann, sent_at_offset=5)
        self._send(self.ann, sent_at_offset=2)

        row = self._rows_by_username(hide_messaged=False)["ann"]

        self.assertIsNotNone(row["last_messaged"])
        self.assertEqual(row["last_messaged"]["send_id"], newest.pk)
        self.assertEqual(row["last_messaged"]["sent_at"], newest.sent_at)
        self.assertEqual(row["last_messaged"]["by"], "pool_sender_dc")
        self.assertFalse(row["last_messaged"]["can_undo"])

    def test_earning_send_exists_flag(self) -> None:
        self._send(self.ann, sent_at_offset=0)
        PromoSend.objects.create(
            organization=self.org,
            event=self.event,
            recipient=self.bob,
            sender=self.sender,
            text="hi",
            earns_points=True,
        )

        rows = self._rows_by_username(hide_messaged=False)

        self.assertFalse(rows["ann"]["earning_send_exists"])
        self.assertTrue(rows["bob"]["earning_send_exists"])

    def test_sends_for_other_events_ignored(self) -> None:
        other_event = Event.objects.create(
            organization=self.org,
            name="Other Event",
            scheduled_at=self.now + timedelta(days=5),
            created_by=self.owner,
        )
        PromoSend.objects.create(
            organization=self.org,
            event=other_event,
            recipient=self.ann,
            sender=self.sender,
            text="hi",
            earns_points=True,
        )

        rows = self._rows_by_username()

        self.assertIn("ann", rows)
        self.assertIsNone(rows["ann"]["last_messaged"])
        self.assertFalse(rows["ann"]["earning_send_exists"])

    def test_name_search(self) -> None:
        self.assertEqual(set(self._rows_by_username(q="AN")), {"ann"})
        self.assertEqual(set(self._rows_by_username(q="bob_dc")), {"bob"})

    def test_ordered_by_recent_count(self) -> None:
        self._tournament([self.bob], days_ago=2, league=self.league)

        rows = candidates(self.org, self.event, n=3, sender=self.sender)

        self.assertEqual([r["username"] for r in rows], ["bob", "ann"])
