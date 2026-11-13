from datetime import timedelta
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.db.models import Sum
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient

from app.discord_accounts import merge_discord_accounts
from app.models import CustomUser, Organization, ProfileClaimRequest
from events.models import Event
from org.contributions.kinds import ContributionKind
from org.contributions.services import reassign_member, repoint_user_attribution
from org.feature_keys import FeatureKey
from org.models import ContributionEntry, ContributionPointValue, OrgFeature, OrgUser


class _LedgerFixture(TestCase):
    def setUp(self) -> None:
        self.owner = CustomUser.objects.create_user(
            username="merge_owner", password="x"
        )
        self.org = Organization.objects.create(name="Merge Org", owner=self.owner)
        self.other_org = Organization.objects.create(
            name="Other Merge Org", owner=self.owner
        )
        self.event_a = self._event("Event A")
        self.event_b = self._event("Event B")

    def _event(self, name: str) -> Event:
        return Event.objects.create(
            organization=self.org,
            name=name,
            scheduled_at=timezone.now() + timedelta(days=1),
            created_by=self.owner,
        )

    def _entry(
        self,
        org_user: OrgUser,
        kind: str,
        points: int,
        event: Event | None = None,
        awarded_by: CustomUser | None = None,
    ) -> ContributionEntry:
        return ContributionEntry.objects.create(
            org_user=org_user,
            organization=org_user.organization,
            kind=kind,
            points=points,
            event=event,
            event_name=event.name if event is not None else "",
            reason="thanks" if kind == ContributionKind.MANUAL else "",
            awarded_by=awarded_by,
            occurred_at=timezone.now(),
        )

    def _total(self, org_user: OrgUser) -> int:
        return (
            ContributionEntry.objects.nocache()
            .filter(org_user=org_user)
            .aggregate(total=Sum("points"))["total"]
            or 0
        )


class ReassignMemberTest(_LedgerFixture):
    def setUp(self) -> None:
        super().setUp()
        self.keep_user = CustomUser.objects.create_user(username="keep_u", password="x")
        self.drop_user = CustomUser.objects.create_user(username="drop_u", password="x")
        self.keep = OrgUser.objects.create(user=self.keep_user, organization=self.org)
        self.drop = OrgUser.objects.create(user=self.drop_user, organization=self.org)

    def test_different_orgs_rejected(self) -> None:
        foreign = OrgUser.objects.create(
            user=self.drop_user, organization=self.other_org
        )
        with self.assertRaises(ValueError):
            reassign_member(foreign, self.keep)

    def test_moves_entries_and_drops_duplicate_staff_entry(self) -> None:
        self._entry(self.keep, ContributionKind.EVENT_HOST, 10, self.event_a)
        self._entry(self.drop, ContributionKind.EVENT_HOST, 10, self.event_a)
        self._entry(self.drop, ContributionKind.EVENT_HOST, 10, self.event_b)
        self._entry(self.drop, ContributionKind.MANUAL, 7, self.event_a)

        moved = reassign_member(self.drop, self.keep)

        self.assertEqual(moved, 2)
        self.assertEqual(self._total(self.keep), 27)
        self.assertFalse(
            ContributionEntry.objects.nocache().filter(org_user=self.drop).exists()
        )

    def test_host_and_helper_on_same_event_keeps_host(self) -> None:
        self._entry(self.keep, ContributionKind.EVENT_HOST, 10, self.event_a)
        self._entry(self.drop, ContributionKind.EVENT_HELPER, 5, self.event_a)

        reassign_member(self.drop, self.keep)

        kinds = list(
            ContributionEntry.objects.nocache()
            .filter(org_user=self.keep, event=self.event_a)
            .values_list("kind", flat=True)
        )
        self.assertEqual(kinds, [ContributionKind.EVENT_HOST])

    def test_drop_host_and_keep_helper_on_same_event_keeps_host(self) -> None:
        self._entry(self.keep, ContributionKind.EVENT_HELPER, 5, self.event_a)
        self._entry(self.drop, ContributionKind.EVENT_HOST, 10, self.event_a)

        reassign_member(self.drop, self.keep)

        kinds = list(
            ContributionEntry.objects.nocache()
            .filter(org_user=self.keep, event=self.event_a)
            .values_list("kind", flat=True)
        )
        self.assertEqual(kinds, [ContributionKind.EVENT_HOST])
        self.assertEqual(self._total(self.keep), 10)


class RepointAttributionTest(_LedgerFixture):
    def test_repoints_hidden_attribution_fks(self) -> None:
        drop = CustomUser.objects.create_user(username="attr_drop", password="x")
        keep = CustomUser.objects.create_user(username="attr_keep", password="x")
        member = OrgUser.objects.create(
            user=CustomUser.objects.create_user(username="m", password="x"),
            organization=self.org,
        )
        entry = self._entry(member, ContributionKind.MANUAL, 3, awarded_by=drop)
        feature = OrgFeature.objects.create(
            organization=self.org,
            feature=FeatureKey.CONTRIBUTIONS,
            enabled=True,
            enabled_by=drop,
        )
        value = ContributionPointValue.objects.create(
            organization=self.org,
            kind=ContributionKind.EVENT_HOST,
            points=20,
            updated_by=drop,
        )

        changed = repoint_user_attribution(drop, keep)

        self.assertEqual(changed, 3)
        entry.refresh_from_db()
        feature.refresh_from_db()
        value.refresh_from_db()
        self.assertEqual(entry.awarded_by_id, keep.pk)
        self.assertEqual(feature.enabled_by_id, keep.pk)
        self.assertEqual(value.updated_by_id, keep.pk)


class ClaimMergeContributionsTest(_LedgerFixture):
    def setUp(self) -> None:
        super().setUp()
        self.admin = CustomUser.objects.create_superuser(
            username="claim_merge_admin", password="x"
        )
        self.target = CustomUser.objects.create_user(
            username="claim_target_u", password="x"
        )
        self.claimer = CustomUser.objects.create_user(
            username="claim_claimer_u", password="x", discordId="777000111"
        )
        self.target_ou = OrgUser.objects.create(user=self.target, organization=self.org)
        self.claimer_ou = OrgUser.objects.create(
            user=self.claimer, organization=self.org
        )
        self.claim = ProfileClaimRequest.objects.create(
            claimer=self.claimer,
            target_user=self.target,
            organization=self.org,
            status=ProfileClaimRequest.Status.PENDING,
        )
        self.client = APIClient()
        self.client.force_authenticate(self.admin)

    def _approve(self) -> None:
        response = self.client.post(f"/api/claim-requests/{self.claim.pk}/approve/")
        self.assertEqual(response.status_code, 200, response.content)

    def test_points_summed_across_both_accounts(self) -> None:
        self._entry(self.target_ou, ContributionKind.MANUAL, 4)
        self._entry(self.target_ou, ContributionKind.EVENT_HOST, 10, self.event_a)
        self._entry(self.claimer_ou, ContributionKind.MANUAL, 2)
        self._entry(self.claimer_ou, ContributionKind.EVENT_HOST, 10, self.event_b)

        self._approve()

        self.assertFalse(CustomUser.objects.filter(pk=self.target.pk).exists())
        self.assertEqual(self._total(self.claimer_ou), 26)

    def test_same_event_host_on_both_keeps_one(self) -> None:
        self._entry(self.target_ou, ContributionKind.EVENT_HOST, 10, self.event_a)
        self._entry(self.claimer_ou, ContributionKind.EVENT_HOST, 10, self.event_a)

        self._approve()

        self.assertEqual(
            ContributionEntry.objects.nocache()
            .filter(event=self.event_a, kind=ContributionKind.EVENT_HOST)
            .count(),
            1,
        )
        self.assertEqual(self._total(self.claimer_ou), 10)

    def test_target_host_claimer_helper_same_event(self) -> None:
        self._entry(self.target_ou, ContributionKind.EVENT_HOST, 10, self.event_a)
        self._entry(self.claimer_ou, ContributionKind.EVENT_HELPER, 5, self.event_a)

        self._approve()

        remaining = list(
            ContributionEntry.objects.nocache()
            .filter(event=self.event_a)
            .values_list("kind", "org_user_id")
        )
        self.assertEqual(remaining, [(ContributionKind.EVENT_HOST, self.claimer_ou.pk)])
        self.assertEqual(self._total(self.claimer_ou), 10)

    def test_target_attribution_moves_to_claimer(self) -> None:
        entry = self._entry(
            self.claimer_ou, ContributionKind.MANUAL, 3, awarded_by=self.target
        )
        feature = OrgFeature.objects.create(
            organization=self.org,
            feature=FeatureKey.CONTRIBUTIONS,
            enabled=True,
            enabled_by=self.target,
        )

        self._approve()

        entry.refresh_from_db()
        feature.refresh_from_db()
        self.assertEqual(entry.awarded_by_id, self.claimer.pk)
        self.assertEqual(feature.enabled_by_id, self.claimer.pk)

    def test_promoter_membership_moves_to_claimer(self) -> None:
        self.org.promoters.add(self.target)

        self._approve()

        promoter_ids = set(
            Organization.promoters.through.objects.filter(
                organization=self.org
            ).values_list("customuser_id", flat=True)
        )
        self.assertEqual(promoter_ids, {self.claimer.pk})


class DiscordReclaimContributionsTest(_LedgerFixture):
    def setUp(self) -> None:
        super().setUp()
        self.keep = CustomUser.objects.create(username="dc_keep", discordId="888111")
        self.drop = CustomUser.objects.create(username="dc_drop")
        self.keep_ou = OrgUser.objects.create(user=self.keep, organization=self.org)
        self.drop_ou = OrgUser.objects.create(user=self.drop, organization=self.org)

    def test_points_in_both_accounts_preserved(self) -> None:
        self._entry(self.keep_ou, ContributionKind.MANUAL, 5)
        self._entry(self.keep_ou, ContributionKind.EVENT_HOST, 10, self.event_a)
        self._entry(self.drop_ou, ContributionKind.MANUAL, 3)
        self._entry(self.drop_ou, ContributionKind.EVENT_HELPER, 5, self.event_b)

        merge_discord_accounts(keep=self.keep, drop=self.drop)

        self.assertFalse(CustomUser.objects.filter(pk=self.drop.pk).exists())
        self.assertEqual(self._total(self.keep_ou), 23)

    def test_drop_attribution_moves_to_keep(self) -> None:
        entry = self._entry(
            self.keep_ou, ContributionKind.MANUAL, 3, awarded_by=self.drop
        )
        feature = OrgFeature.objects.create(
            organization=self.org,
            feature=FeatureKey.PROMOTION,
            enabled=True,
            enabled_by=self.drop,
        )

        merge_discord_accounts(keep=self.keep, drop=self.drop)

        entry.refresh_from_db()
        feature.refresh_from_db()
        self.assertEqual(entry.awarded_by_id, self.keep.pk)
        self.assertEqual(feature.enabled_by_id, self.keep.pk)


class UserDeleteWithContributionsTest(_LedgerFixture):
    def setUp(self) -> None:
        super().setUp()
        self.site_admin = CustomUser.objects.create_superuser(
            username="delete_admin", password="x"
        )
        self.victim = CustomUser.objects.create_user(
            username="delete_victim", password="x"
        )
        victim_ou = OrgUser.objects.create(user=self.victim, organization=self.org)
        self._entry(victim_ou, ContributionKind.MANUAL, 4)
        self._entry(victim_ou, ContributionKind.EVENT_HOST, 10, self.event_a)

    def _assert_gone(self) -> None:
        self.assertFalse(CustomUser.objects.filter(pk=self.victim.pk).exists())
        self.assertFalse(
            ContributionEntry.objects.nocache()
            .filter(org_user__user_id=self.victim.pk)
            .exists()
        )
        self.assertEqual(ContributionEntry.objects.nocache().count(), 0)

    def test_api_delete_removes_user_and_entries(self) -> None:
        client = APIClient()
        client.force_authenticate(self.site_admin)
        response = client.delete(reverse("users-detail", args=[self.victim.pk]))
        self.assertEqual(response.status_code, 204, response.content)
        self._assert_gone()

    def test_admin_delete_view_confirms_and_deletes(self) -> None:
        self.client.force_login(self.site_admin)
        url = f"/admin/app/customuser/{self.victim.pk}/delete/"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "protected related objects")
        self.assertNotContains(response, "would require deleting")

        response = self.client.post(url, {"post": "yes"})
        self.assertEqual(response.status_code, 302)
        self._assert_gone()

    def test_admin_bulk_delete_selected_deletes(self) -> None:
        self.client.force_login(self.site_admin)
        response = self.client.post(
            "/admin/app/customuser/",
            {
                "action": "delete_selected",
                "_selected_action": [str(self.victim.pk)],
                "post": "yes",
            },
        )
        self.assertEqual(response.status_code, 302)
        self._assert_gone()

    def test_sync_prod_users_clears_ledger_first(self) -> None:
        Organization.objects.update(owner=None)
        response = MagicMock()
        response.json.return_value = []
        with patch(
            "app.management.commands.sync_prod_users.requests.get",
            return_value=response,
        ):
            call_command("sync_prod_users")
        self._assert_gone()
