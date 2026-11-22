from datetime import datetime

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.test import APIClient

from app.models import CustomUser
from events.tests.base import EventTestCase
from org.contributions import queries
from org.contributions.services import (
    delete_user_entries,
    reassign_member,
    repoint_ledger_attribution,
    user_entries,
)
from org.features import FeatureKey, set_org_feature
from org.models import (
    ContributionEntry,
    ContributionPointValue,
    OrgLog,
    OrgUser,
)
from org.standing import ledger
from org.standing.periods import parse_period


class ContributionTrackFilterTest(EventTestCase):
    def setUp(self) -> None:
        self.now = timezone.now()
        self.member = self.make_user()
        self.member_ou = OrgUser.objects.get(user=self.member, organization=self.org)

    def _leadership(
        self, user: CustomUser, *, awarded_by: CustomUser | None = None
    ) -> ContributionEntry:
        return ledger.award(
            org=self.org,
            user=user,
            kind="captained",
            points=5,
            occurred_at=self.now,
            event=self.event,
            awarded_by=awarded_by,
        )

    def _manual(
        self, user: CustomUser, points: int = 3, *, at: datetime | None = None
    ) -> ContributionEntry:
        return ledger.award(
            org=self.org,
            user=user,
            kind="manual",
            points=points,
            occurred_at=at or self.now,
            reason="thanks",
        )

    def test_award_stores_track(self) -> None:
        self.assertEqual(self._leadership(self.member).track, "leadership")
        self.assertEqual(self._manual(self.member).track, "contribution")

    def test_leadership_row_never_on_contribution_reads(self) -> None:
        lead = self._leadership(self.member)
        self._manual(self.member)
        period = parse_period(self.org, None)
        self.assertEqual(queries.org_total(self.org, period), 3)
        rows = queries.leaderboard(self.org, period)
        self.assertEqual([(r["points"], r["entries"]) for r in rows], [(3, 1)])
        self.assertEqual(queries.member_totals(self.member_ou)["all_time"], 3)
        self.assertEqual(
            sum(m["points"] for m in queries.member_monthly(self.member_ou)), 3
        )
        self.assertEqual(
            [e.kind for e in queries.member_entries(self.member_ou, period)],
            ["manual"],
        )

        set_org_feature(
            self.org, FeatureKey.CONTRIBUTIONS, enabled=True, actor=self.admin
        )
        client = APIClient()
        client.force_authenticate(user=self.admin)
        base = f"/api/organizations/{self.org.pk}/contributions/"
        listed = client.get(f"{base}entries/")
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual(listed.json()["count"], 1)
        patched = client.patch(
            f"{base}entries/{lead.pk}/", {"points": 9}, format="json"
        )
        self.assertEqual(patched.status_code, 404, patched.content)

    def test_delete_user_entries_counts_contribution_only(self) -> None:
        lead = self._leadership(self.member)
        self._manual(self.member)
        self.assertEqual(delete_user_entries(self.member, actor=self.admin), 1)
        log = OrgLog.objects.get(
            organization=self.org, action="delete_user_contributions"
        )
        self.assertEqual(log.details["count"], 1)
        self.assertTrue(ContributionEntry.objects.nocache().filter(pk=lead.pk).exists())

    def test_reassign_member_leaves_leadership_rows(self) -> None:
        keep_user = self.make_user()
        keep_ou = OrgUser.objects.get(user=keep_user, organization=self.org)
        self._leadership(keep_user)
        dropped = self._leadership(self.member)
        reassign_member(self.member_ou, keep_ou)
        dropped.refresh_from_db()
        self.assertEqual(dropped.org_user_id, self.member_ou.pk)

    def test_repoint_ignores_leadership_rows(self) -> None:
        drop = self.make_user()
        keep = self.make_user()
        lead = self._leadership(self.member, awarded_by=drop)
        value = ContributionPointValue.objects.create(
            organization=self.org, kind="captained", points=7, updated_by=drop
        )
        repoint_ledger_attribution(drop, keep)
        lead.refresh_from_db()
        value.refresh_from_db()
        self.assertEqual(lead.awarded_by_id, drop.pk)
        self.assertEqual(value.updated_by_id, drop.pk)

    def test_user_entries_contribution_only(self) -> None:
        self._leadership(self.member)
        manual = self._manual(self.member)
        self.assertEqual(
            list(user_entries([self.member.pk]).values_list("pk", flat=True)),
            [manual.pk],
        )

    def test_once_per_event_constraint(self) -> None:
        for kind in ("event_host", "captained"):
            ContributionEntry.objects.create(
                org_user=self.member_ou,
                organization=self.org,
                track=ledger.KINDS[kind].track,
                kind=kind,
                points=1,
                event=self.event,
                occurred_at=self.now,
            )
            with self.assertRaises(IntegrityError), transaction.atomic():
                ContributionEntry.objects.create(
                    org_user=self.member_ou,
                    organization=self.org,
                    track=ledger.KINDS[kind].track,
                    kind=kind,
                    points=2,
                    event=self.event,
                    occurred_at=self.now,
                )
