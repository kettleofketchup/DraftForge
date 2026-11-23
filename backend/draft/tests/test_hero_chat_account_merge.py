from datetime import date

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from app.discord_accounts import merge_discord_accounts
from app.models import CustomUser, ProfileClaimRequest
from draft.models import HeroDraft, HeroDraftChatMembership, HeroDraftChatMessage
from draft.services.hero import new_herodraft_for_game
from draft.services.hero_chat import repoint_chat_attribution
from org.models import Organization
from tournament.models import Game, Team, Tournament

Channel = HeroDraftChatMessage.Channel


class ChatAccountMergeTest(TestCase):
    def setUp(self) -> None:
        self.drop = CustomUser.objects.create_user(username="chat_drop", password="x")
        self.keep = CustomUser.objects.create_user(username="chat_keep", password="x")
        tournament = Tournament.objects.create(
            name="Merge Chat Tournament", date_played=date.today()
        )
        self.radiant = Team.objects.create(name="Merge R", tournament=tournament)
        self.dire = Team.objects.create(name="Merge D", tournament=tournament)
        self.draft: HeroDraft = new_herodraft_for_game(
            Game.objects.create(
                tournament=tournament, radiant_team=self.radiant, dire_team=self.dire
            )
        )

    def _message(self, sender: CustomUser) -> HeroDraftChatMessage:
        return HeroDraftChatMessage.objects.create(
            draft=self.draft,
            channel=Channel.TEAM,
            team=self.radiant,
            sender=sender,
            body="gl",
        )

    def _membership(self, team: Team, user: CustomUser) -> HeroDraftChatMembership:
        return HeroDraftChatMembership.objects.create(
            draft=self.draft, team=team, user=user, joined_at=timezone.now()
        )

    def _assert_colliding_rows_kept(
        self, drop_row: HeroDraftChatMembership, keep_row: HeroDraftChatMembership
    ) -> None:
        drop_row.refresh_from_db()
        keep_row.refresh_from_db()
        self.assertEqual(drop_row.user_id, self.keep.pk)
        self.assertIsNotNone(drop_row.left_at)
        self.assertIsNone(keep_row.left_at)
        self.assertEqual(
            HeroDraftChatMembership.objects.filter(
                draft=self.draft, user=self.keep, left_at__isnull=True
            ).count(),
            1,
        )

    def test_repoints_sender_and_membership(self) -> None:
        message = self._message(self.drop)
        membership = self._membership(self.radiant, self.drop)

        changed = repoint_chat_attribution(self.drop, self.keep)

        self.assertEqual(changed, 2)
        message.refresh_from_db()
        membership.refresh_from_db()
        self.assertEqual(message.sender_id, self.keep.pk)
        self.assertEqual(membership.user_id, self.keep.pk)
        before = HeroDraftChatMessage.objects.count()
        self.drop.delete()
        self.assertEqual(HeroDraftChatMessage.objects.count(), before)

    def test_open_memberships_in_same_draft_do_not_collide(self) -> None:
        drop_row = self._membership(self.radiant, self.drop)
        keep_row = self._membership(self.dire, self.keep)

        repoint_chat_attribution(self.drop, self.keep)

        self._assert_colliding_rows_kept(drop_row, keep_row)

    def test_discord_merge_keeps_chat_history(self) -> None:
        message = self._message(self.drop)
        drop_row = self._membership(self.radiant, self.drop)
        keep_row = self._membership(self.dire, self.keep)

        merge_discord_accounts(self.keep, self.drop)

        message.refresh_from_db()
        self.assertEqual(message.sender_id, self.keep.pk)
        self._assert_colliding_rows_kept(drop_row, keep_row)

    def test_profile_claim_keeps_chat_history(self) -> None:
        admin = CustomUser.objects.create_superuser(username="chat_admin", password="x")
        org = Organization.objects.create(name="Chat Merge Org", owner=admin)
        claim = ProfileClaimRequest.objects.create(
            claimer=self.keep,
            target_user=self.drop,
            organization=org,
            status=ProfileClaimRequest.Status.PENDING,
        )
        message = self._message(self.drop)
        drop_row = self._membership(self.radiant, self.drop)
        keep_row = self._membership(self.dire, self.keep)
        client = APIClient()
        client.force_authenticate(admin)

        response = client.post(f"/api/claim-requests/{claim.pk}/approve/")

        self.assertEqual(response.status_code, 200, response.content)
        message.refresh_from_db()
        self.assertEqual(message.sender_id, self.keep.pk)
        self._assert_colliding_rows_kept(drop_row, keep_row)
