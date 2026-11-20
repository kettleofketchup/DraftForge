from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from app.models import CustomUser, Organization, OrgLog
from events.constants import EventState
from events.models import Event
from org.contributions.adapter import CONTRIBUTION
from org.contributions.queries import leaderboard as contribution_leaderboard
from org.contributions.queries import org_total
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.models import ContributionEntry, OrgUser
from org.standing import api as standing
from org.standing import registry
from org.standing.periods import parse_period
from org.standing.types import TrackAccess


@override_settings(CACHEOPS_ENABLED=False)
class ContributionAdapterTest(TestCase):
    def setUp(self) -> None:
        self.owner = CustomUser.objects.create_user(
            username="ca_owner", password="x", is_staff=True
        )
        self.host = CustomUser.objects.create_user(username="ca_host", password="x")
        self.org = Organization.objects.create(name="CA Org", owner=self.owner)
        self.host_ou = OrgUser.objects.create(user=self.host, organization=self.org)
        self.event = Event.objects.create(
            organization=self.org,
            name="CA Event",
            scheduled_at=timezone.now() - timedelta(hours=2),
            created_by=self.owner,
            host=self.host,
            state=EventState.COMPLETED,
        )

    def _close(self, *, cancelled: bool, source: str) -> standing.HookResult:
        with transaction.atomic():
            return standing.on_event_closed(
                self.event,
                cancelled=cancelled,
                source=source,
                actor=None,  # type: ignore[arg-type]
            )

    def _entries(self) -> int:
        return ContributionEntry.objects.nocache().filter(event=self.event).count()

    def test_registry_holds_contribution(self) -> None:
        self.assertEqual([t.key for t in registry.tracks()], ["contribution"])

    def test_close_completed_awards_and_stamps(self) -> None:
        result = self._close(cancelled=False, source="admin")
        self.assertEqual(result.orglog_details(), {"awarded": self._entries()})
        self.assertGreater(self._entries(), 0)
        self.assertIsNotNone(self.event.contributions_awarded_at)
        self.assertIsNotNone(
            Event.objects.nocache().get(pk=self.event.pk).contributions_awarded_at
        )

    def test_close_admin_cancel_no_award(self) -> None:
        result = self._close(cancelled=True, source="admin")
        self.assertEqual(result.orglog_details(), {"awarded": 0})
        self.assertEqual(result.log_fields(), {"awarded": False, "created": 0})
        self.assertEqual(self._entries(), 0)

    def test_close_auto_cancel_with_host_awards(self) -> None:
        result = self._close(cancelled=True, source="auto")
        self.assertTrue(result.log_fields()["awarded"])
        self.assertGreater(self._entries(), 0)

    def test_close_awards_while_feature_locked(self) -> None:
        set_org_feature(
            self.org, FeatureKey.CONTRIBUTIONS, enabled=False, actor=self.owner
        )
        self._close(cancelled=False, source="admin")
        self.assertGreater(self._entries(), 0)

    def test_reopen_revokes_staff_only(self) -> None:
        self._close(cancelled=False, source="admin")
        staff = self._entries()
        ContributionEntry.objects.create(
            organization=self.org,
            org_user=self.host_ou,
            kind="manual",
            points=3,
            event=self.event,
            reason="thanks",
            occurred_at=timezone.now(),
        )
        with transaction.atomic():
            result = standing.on_event_reopened(self.event, actor=None)
        self.assertEqual(result.orglog_details(), {"revoked": staff})
        self.assertEqual(result.log_fields(), {"revoked": staff})
        self.assertEqual(self._entries(), 1)

    def test_changed_without_staff_field_does_not_sync(self) -> None:
        with transaction.atomic():
            result = standing.on_event_changed(
                self.event, fields=frozenset({"description"})
            )
        self.assertEqual(self._entries(), 0)
        self.assertIn("synced", result.log_fields())

    def test_changed_open_event_reports_synced_false(self) -> None:
        self.event.state = EventState.SIGNUPS_OPEN
        with transaction.atomic():
            result = standing.on_event_changed(self.event, fields=frozenset({"name"}))
        self.assertEqual(result.log_fields(), {"synced": False})

    def test_reopen_reset_fields(self) -> None:
        self.assertEqual(
            standing.reopen_reset_fields(), {"contributions_awarded_at": None}
        )

    def test_deletion_blockers_lazy(self) -> None:
        with self.assertNumQueries(0):
            blockers = standing.deletion_blockers([self.host.pk])
        self.assertEqual(len(blockers), 1)

    def test_user_deleted_logs_per_org(self) -> None:
        self._close(cancelled=False, source="admin")
        with transaction.atomic():
            standing.on_user_deleted(self.host, actor=self.owner)
        self.assertEqual(
            ContributionEntry.objects.nocache().filter(org_user=self.host_ou).count(), 0
        )
        self.assertTrue(
            OrgLog.objects.filter(
                organization=self.org, action="delete_user_contributions"
            ).exists()
        )

    def test_leaderboard_through_api(self) -> None:
        set_org_feature(
            self.org, FeatureKey.CONTRIBUTIONS, enabled=True, actor=self.owner
        )
        self._close(cancelled=False, source="admin")
        period = parse_period(self.org, None)
        board = standing.leaderboard(
            self.org, "contribution", "points", period, viewer=self.owner
        )
        expected = contribution_leaderboard(self.org, period)
        self.assertEqual(
            [{**r.member, "points": r.value, "entries": r.sample} for r in board.rows],
            expected,
        )
        self.assertEqual(board.total, org_total(self.org, period))
        anon = standing.leaderboard(
            self.org, "contribution", "points", period, viewer=AnonymousUser()
        )
        self.assertEqual(tuple(anon.rows), ())
        self.assertFalse(anon.rows_visible)
        self.assertEqual(anon.total, board.total)

    def test_access_viewer_none(self) -> None:
        with self.assertNumQueries(0):
            access = CONTRIBUTION.access(self.org.pk, viewer=None)
        self.assertEqual(access, TrackAccess(False, False))
