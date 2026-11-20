from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.db import transaction
from django.utils import timezone as tz
from rest_framework.test import APIClient

from app.discord_accounts import merge_discord_accounts
from app.models import CustomUser, ProfileClaimRequest
from org.models import Organization
from events.constants import EventState
from events.models import Event
from org.conduct.constants import Outcome, OutcomeSource
from org.conduct.services import reassign_member
from org.models import AttendanceOutcome, OrgConductSettings, OrgUser
from org.standing import api as standing
from org.tests.conduct_base import ConductTestCase


class _MergeFixture(ConductTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.drop_user = CustomUser.objects.create_user(
            username="conduct_drop", password="x"
        )
        self.keep_user = CustomUser.objects.create_user(
            username="conduct_keep", password="x", discordId="555000111"
        )
        self.drop = self.org_user(self.drop_user)
        self.keep = self.org_user(self.keep_user)
        self.event_b = Event.objects.create(
            organization=self.org,
            name="Second Event",
            scheduled_at=tz.now() - timedelta(days=2),
            state=EventState.COMPLETED,
            created_by=self.admin,
        )

    def rows(self, org_user: OrgUser) -> list[tuple[int | None, str, str]]:
        return sorted(
            AttendanceOutcome.objects.nocache()
            .filter(org_user=org_user)
            .values_list("event_id", "outcome", "source"),
            key=lambda r: r[0] or 0,
        )


class ReassignConductMemberTest(_MergeFixture):
    def test_moves_rows(self) -> None:
        self.outcome(self.drop_user, event=self.event, outcome=Outcome.NO_SHOW)
        self.outcome(self.drop_user, event=None)
        self.outcome(self.keep_user, event=self.event_b)

        moved = reassign_member(self.drop, self.keep)

        self.assertEqual(moved, 2)
        self.assertEqual(self.rows(self.drop), [])
        self.assertEqual(
            self.rows(self.keep),
            [
                (None, Outcome.ATTENDED, OutcomeSource.DEFAULT),
                (self.event.pk, Outcome.NO_SHOW, OutcomeSource.DEFAULT),
                (self.event_b.pk, Outcome.ATTENDED, OutcomeSource.DEFAULT),
            ],
        )

    def test_conflict_keeps_staff_row(self) -> None:
        drop_row = self.outcome(
            self.drop_user,
            event=self.event,
            outcome=Outcome.NO_SHOW,
            source=OutcomeSource.STAFF,
            reason="missed it",
        )
        self.outcome(self.keep_user, event=self.event)

        moved = reassign_member(self.drop, self.keep)

        self.assertEqual(moved, 1)
        rows = list(
            AttendanceOutcome.objects.nocache()
            .filter(event=self.event)
            .values_list("pk", "org_user_id", "outcome")
        )
        self.assertEqual(rows, [(drop_row.pk, self.keep.pk, Outcome.NO_SHOW)])

    def test_conflict_both_staff_keeps_keep(self) -> None:
        self.outcome(
            self.drop_user,
            event=self.event,
            outcome=Outcome.NO_SHOW,
            source=OutcomeSource.STAFF,
            reason="drop reason",
        )
        keep_row = self.outcome(
            self.keep_user,
            event=self.event,
            outcome=Outcome.EXCUSED,
            source=OutcomeSource.STAFF,
            reason="keep reason",
        )

        moved = reassign_member(self.drop, self.keep)

        self.assertEqual(moved, 0)
        rows = list(
            AttendanceOutcome.objects.nocache()
            .filter(event=self.event)
            .values_list("pk", "org_user_id")
        )
        self.assertEqual(rows, [(keep_row.pk, self.keep.pk)])

    def test_conflict_neither_staff_keeps_keep(self) -> None:
        self.outcome(self.drop_user, event=self.event, outcome=Outcome.NO_SHOW)
        keep_row = self.outcome(self.keep_user, event=self.event)

        reassign_member(self.drop, self.keep)

        rows = list(
            AttendanceOutcome.objects.nocache()
            .filter(event=self.event)
            .values_list("pk", flat=True)
        )
        self.assertEqual(rows, [keep_row.pk])

    def test_same_member_is_noop(self) -> None:
        self.outcome(self.drop_user, event=self.event)
        self.assertEqual(reassign_member(self.drop, self.drop), 0)
        self.assertEqual(len(self.rows(self.drop)), 1)

    def test_cross_org_raises(self) -> None:
        other = Organization.objects.create(name="Other Conduct Org")
        stranger = OrgUser.objects.create(user=self.keep_user, organization=other)
        self.outcome(self.drop_user, event=self.event)

        with self.assertRaisesMessage(
            ValueError, "cannot reassign conduct across organizations"
        ):
            reassign_member(self.drop, stranger)
        self.assertEqual(len(self.rows(self.drop)), 1)


class ClaimMergeConductTest(_MergeFixture):
    def test_claim_merge_calls_conduct(self) -> None:
        superuser = CustomUser.objects.create_superuser(
            username="conduct_claim_admin", password="x"
        )
        claim = ProfileClaimRequest.objects.create(
            claimer=self.keep_user,
            target_user=self.drop_user,
            organization=self.org,
            status=ProfileClaimRequest.Status.PENDING,
        )
        self.outcome(self.drop_user, event=self.event, outcome=Outcome.NO_SHOW)
        client = APIClient()
        client.force_authenticate(superuser)

        response = client.post(f"/api/claim-requests/{claim.pk}/approve/")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(CustomUser.objects.filter(pk=self.drop_user.pk).exists())
        self.assertEqual(
            self.rows(self.keep),
            [(self.event.pk, Outcome.NO_SHOW, OutcomeSource.DEFAULT)],
        )


class DiscordReclaimConductTest(_MergeFixture):
    def test_discord_reclaim_calls_conduct(self) -> None:
        self.outcome(self.drop_user, event=self.event, outcome=Outcome.LATE_CANCEL)

        merge_discord_accounts(keep=self.keep_user, drop=self.drop_user)

        self.assertFalse(CustomUser.objects.filter(pk=self.drop_user.pk).exists())
        self.assertEqual(
            self.rows(self.keep),
            [(self.event.pk, Outcome.LATE_CANCEL, OutcomeSource.DEFAULT)],
        )


class RepointConductAttributionTest(_MergeFixture):
    def test_repoint_attribution_includes_conduct(self) -> None:
        row = self.outcome(
            self.keep_user,
            event=self.event,
            outcome=Outcome.NO_SHOW,
            source=OutcomeSource.STAFF,
            reason="noted",
            set_by=self.drop_user,
        )
        conduct_settings = OrgConductSettings.objects.create(
            organization=self.org, updated_by=self.drop_user
        )

        with transaction.atomic():
            standing.merge_users(self.drop_user, self.keep_user, member_pairs=[])

        row.refresh_from_db()
        self.assertEqual(row.set_by_id, self.keep_user.pk)
        self.assertEqual(
            OrgConductSettings.objects.nocache()
            .get(pk=conduct_settings.pk)
            .updated_by_id,
            self.keep_user.pk,
        )


class SyncProdUsersConductTest(_MergeFixture):
    def test_sync_prod_users_clears_outcomes(self) -> None:
        self.outcome(
            self.keep_user,
            event=self.event,
            outcome=Outcome.NO_SHOW,
            source=OutcomeSource.STAFF,
            reason="noted",
            set_by=self.drop_user,
        )
        Organization.objects.update(owner=None)
        response = MagicMock()
        response.json.return_value = []
        with patch(
            "app.management.commands.sync_prod_users.requests.get",
            return_value=response,
        ):
            call_command("sync_prod_users")
        self.assertFalse(AttendanceOutcome.objects.nocache().exists())
