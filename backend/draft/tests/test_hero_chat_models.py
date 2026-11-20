from datetime import date

from django.conf import settings
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from app.models import CustomUser, Game, Team, Tournament
from draft.models import HeroDraft, HeroDraftChatMembership, HeroDraftChatMessage
from draft.services.hero import new_herodraft_for_game
from org.contributions.services import repoint_user_attribution

Channel = HeroDraftChatMessage.Channel
Kind = HeroDraftChatMessage.Kind


class HeroDraftChatModelTest(TestCase):
    def setUp(self) -> None:
        self.cap1 = CustomUser.objects.create_user(username="chat_cap1", password="x")
        self.cap2 = CustomUser.objects.create_user(username="chat_cap2", password="x")
        self.tournament = Tournament.objects.create(
            name="Chat Tournament", date_played=date.today()
        )
        self.team1 = Team.objects.create(
            name="Chat T1", tournament=self.tournament, captain=self.cap1
        )
        self.team2 = Team.objects.create(
            name="Chat T2", tournament=self.tournament, captain=self.cap2
        )
        self.game = Game.objects.create(
            tournament=self.tournament, radiant_team=self.team1, dire_team=self.team2
        )
        self.draft: HeroDraft = new_herodraft_for_game(self.game)

    def _msg(self, **kwargs: object) -> HeroDraftChatMessage:
        fields: dict[str, object] = {
            "draft": self.draft,
            "channel": Channel.TEAM,
            "team": self.team1,
            "sender": self.cap1,
            "kind": Kind.TEXT,
            "body": "hello",
        }
        fields.update(kwargs)
        return HeroDraftChatMessage.objects.create(**fields)

    def _assert_integrity(self, **kwargs: object) -> None:
        with self.assertRaises(IntegrityError), transaction.atomic():
            self._msg(**kwargs)

    def test_team_channel_requires_team(self) -> None:
        self._assert_integrity(channel=Channel.TEAM, team=None)

    def test_all_channel_forbids_team(self) -> None:
        self._assert_integrity(channel=Channel.ALL, team=self.team1)

    def test_all_channel_without_team_is_valid(self) -> None:
        msg = self._msg(channel=Channel.ALL, team=None)
        self.assertIsNone(msg.team_id)

    def test_suggestion_must_be_team_channel(self) -> None:
        self._assert_integrity(
            channel=Channel.ALL, team=None, kind=Kind.SUGGEST_BAN, hero_id=1, body=""
        )

    def test_suggestion_requires_hero(self) -> None:
        self._assert_integrity(kind=Kind.SUGGEST_PICK, hero_id=None, body="")

    def test_suggestion_on_team_channel_is_valid(self) -> None:
        msg = self._msg(kind=Kind.SUGGEST_PICK, hero_id=5, body="")
        self.assertEqual(msg.hero_id, 5)

    def test_text_requires_body_and_no_hero(self) -> None:
        self._assert_integrity(kind=Kind.TEXT, body="")
        self._assert_integrity(kind=Kind.TEXT, body="x", hero_id=5)

    def test_team_delete_cascades_chat(self) -> None:
        self._msg()
        self._msg(channel=Channel.ALL, team=None)
        team_pk = self.team1.pk
        self.team1.delete()
        self.assertFalse(HeroDraftChatMessage.objects.filter(team_id=team_pk).exists())
        self.assertFalse(
            HeroDraftChatMessage.objects.filter(
                channel=Channel.TEAM, team__isnull=True
            ).exists()
        )

    def test_not_cached(self) -> None:
        self.assertNotIn("draft.herodraftchatmessage", settings.CACHEOPS)
        self.assertNotIn("draft.herodraftchatmembership", settings.CACHEOPS)
        self.assertNotIn("app.*", settings.CACHEOPS)
        self.assertNotIn("draft.*", settings.CACHEOPS)

    def test_public_id_unique_and_ordering(self) -> None:
        first = self._msg()
        second = self._msg(channel=Channel.ALL, team=None)
        self.assertNotEqual(first.public_id, second.public_id)
        self.assertEqual(
            list(HeroDraftChatMessage.objects.filter(draft=self.draft)),
            [first, second],
        )

    def test_open_membership_unique(self) -> None:
        now = timezone.now()
        HeroDraftChatMembership.objects.filter(draft=self.draft).delete()
        HeroDraftChatMembership.objects.create(
            draft=self.draft, team=self.team1, user=self.cap1, joined_at=now
        )
        with self.assertRaises(IntegrityError), transaction.atomic():
            HeroDraftChatMembership.objects.create(
                draft=self.draft, team=self.team2, user=self.cap1, joined_at=now
            )
        HeroDraftChatMembership.objects.create(
            draft=self.draft,
            team=self.team2,
            user=self.cap1,
            joined_at=now,
            left_at=now,
        )
        self.assertEqual(
            HeroDraftChatMembership.objects.filter(
                draft=self.draft, user=self.cap1
            ).count(),
            2,
        )

    def test_merge_repoints_chat(self) -> None:
        drop = CustomUser.objects.create_user(username="chat_drop", password="x")
        keep = CustomUser.objects.create_user(username="chat_keep", password="x")
        msg = self._msg(sender=drop)
        membership = HeroDraftChatMembership.objects.create(
            draft=self.draft, team=self.team1, user=drop, joined_at=timezone.now()
        )

        changed = repoint_user_attribution(drop, keep)

        self.assertEqual(changed, 2)
        msg.refresh_from_db()
        membership.refresh_from_db()
        self.assertEqual(msg.sender_id, keep.pk)
        self.assertEqual(membership.user_id, keep.pk)
        before = HeroDraftChatMessage.objects.count()
        drop.delete()
        self.assertEqual(HeroDraftChatMessage.objects.count(), before)
