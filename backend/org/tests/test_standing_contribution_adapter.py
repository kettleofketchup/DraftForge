from datetime import datetime, timedelta

from django.contrib.auth.models import AnonymousUser
from django.db import connection, transaction
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from app.models import CustomUser
from events.constants import EventState
from events.models import Event
from org.accounts import repoint_org_attribution
from org.contributions.adapter import CONTRIBUTION
from org.contributions.queries import leaderboard as contribution_leaderboard
from org.contributions.queries import org_total
from org.contributions.services import (
    has_promo_entry,
    promo_points,
    revoke_promo_entry,
)
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.models import (
    ContributionEntry,
    Organization,
    OrgFeature,
    OrgLog,
    OrgUser,
    PromoSend,
    PromoTemplate,
)
from org.standing import api as standing
from org.standing import registry
from org.standing.periods import parse_period
from org.standing.types import CloseSource, TrackAccess, ViewerRoles


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

    def _close(
        self, *, cancelled: bool, source: CloseSource, now: datetime | None = None
    ) -> standing.HookResult:
        with transaction.atomic():
            return standing.on_event_closed(
                self.event,
                cancelled=cancelled,
                source=source,
                actor=None,
                now=now,
            )

    def _add_helpers(self, count: int) -> None:
        for i in range(count):
            helper = CustomUser.objects.create_user(
                username=f"ca_helper{i}", password="x"
            )
            OrgUser.objects.create(user=helper, organization=self.org)
            self.event.helpers.add(helper)

    def _entries(self) -> int:
        return ContributionEntry.objects.nocache().filter(event=self.event).count()

    def test_registry_holds_contribution(self) -> None:
        self.assertEqual(
            [t.key for t in registry.tracks()],
            ["contribution", "conduct", "leadership"],
        )

    def test_close_completed_awards_and_stamps(self) -> None:
        self._add_helpers(2)
        now = timezone.now()
        result = self._close(cancelled=False, source="admin", now=now)
        self.assertEqual(
            result.orglog_details(),
            {"awarded": 3, "captains_snapshotted": 0, "leadership_awarded": 0},
        )
        self.assertEqual(result.log_fields(), {"awarded": True, "created": 3})
        self.assertEqual(self._entries(), 3)
        self.assertEqual(self.event.contributions_awarded_at, now)
        self.assertEqual(
            Event.objects.nocache().get(pk=self.event.pk).contributions_awarded_at, now
        )

    def test_close_admin_cancel_no_award(self) -> None:
        result = self._close(cancelled=True, source="admin")
        self.assertEqual(
            result.orglog_details(),
            {"awarded": 0, "captains_snapshotted": 0, "leadership_awarded": 0},
        )
        self.assertEqual(result.log_fields(), {"awarded": False, "created": 0})
        self.assertEqual(self._entries(), 0)

    def test_close_auto_cancel_with_host_awards(self) -> None:
        result = self._close(cancelled=True, source="auto")
        self.assertTrue(result.log_fields()["awarded"])
        self.assertGreater(self._entries(), 0)

    def test_close_auto_cancel_with_helpers_awards(self) -> None:
        self.event.host = None
        self.event.save(update_fields=["host"])
        self._add_helpers(1)
        result = self._close(cancelled=True, source="auto")
        self.assertEqual(result.log_fields(), {"awarded": True, "created": 1})
        self.assertEqual(self._entries(), 1)

    def test_close_auto_cancel_without_staff_no_award(self) -> None:
        self.event.host = None
        self.event.save(update_fields=["host"])
        result = self._close(cancelled=True, source="auto")
        self.assertEqual(result.log_fields(), {"awarded": False, "created": 0})
        self.assertIsNone(self.event.contributions_awarded_at)

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
        self.assertEqual(
            result.orglog_details(),
            {
                "revoked": staff,
                "attendance_reopened": 0,
                "captain_reviews_voided": 0,
                "leadership_revoked": 0,
            },
        )
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
            standing.reopen_reset_fields(),
            {"contributions_awarded_at": None, "conduct_finalized_at": None},
        )

    def test_deletion_blockers_lazy(self) -> None:
        with self.assertNumQueries(0):
            blockers = standing.deletion_blockers([self.host.pk])
        self.assertEqual(len(blockers), 2)

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
            access = CONTRIBUTION.access(
                self.org.pk, viewer=None, roles=ViewerRoles.fixed(False, False, False)
            )
        self.assertEqual(access, TrackAccess(False, False))

    def _award_entries(self) -> None:
        set_org_feature(
            self.org, FeatureKey.CONTRIBUTIONS, enabled=True, actor=self.owner
        )
        self._add_helpers(2)
        self._close(cancelled=False, source="admin")
        helper = CustomUser.objects.get(username="ca_helper0")
        second = Event.objects.create(
            organization=self.org,
            name="CA Event 2",
            scheduled_at=timezone.now() - timedelta(hours=1),
            created_by=self.owner,
            host=helper,
            state=EventState.COMPLETED,
        )
        with transaction.atomic():
            standing.on_event_closed(
                second, cancelled=False, source="admin", actor=None
            )

    def test_entries_metric_declared_not_default(self) -> None:
        entries = next(m for m in CONTRIBUTION.metrics if m.key == "entries")
        self.assertEqual(
            (entries.label, entries.format, entries.periodic, entries.default),
            ("Entries", "int", True, False),
        )

    def test_entries_metric_matches_legacy_entries(self) -> None:
        self._award_entries()
        period = parse_period(self.org, None)
        board = standing.leaderboard(
            self.org, "contribution", "entries", period, viewer=self.owner
        )
        legacy = contribution_leaderboard(self.org, period)
        by_member = {r["org_user_pk"]: r["entries"] for r in legacy}
        self.assertEqual({r.org_user_id: r.value for r in board.rows}, by_member)
        self.assertEqual({r.org_user_id: r.sample for r in board.rows}, by_member)
        values = [r.value for r in board.rows]
        self.assertEqual(values, sorted(values, reverse=True))
        self.assertEqual(board.metric.key, "entries")

    def test_entries_metric_same_query_count_as_points(self) -> None:
        self._award_entries()
        period = parse_period(self.org, None)
        counts: dict[str, int] = {}
        for metric in ("points", "entries"):
            with CaptureQueriesContext(connection) as ctx:
                standing.leaderboard(
                    self.org, "contribution", metric, period, viewer=self.owner
                )
            counts[metric] = len(ctx.captured_queries)
        self.assertEqual(counts["entries"], counts["points"])

    def test_member_standing_payload(self) -> None:
        self._award_entries()
        block = CONTRIBUTION.member_standing(
            self.host_ou,
            viewer=self.host,
            roles=ViewerRoles.fixed(False, False, False),
            now=timezone.now(),
        )
        assert block is not None
        self.assertEqual(set(block), {"totals", "monthly"})

    def test_member_standing_budget(self) -> None:
        self._award_entries()
        with self.assertNumQueries(2):
            CONTRIBUTION.member_standing(
                self.host_ou,
                viewer=self.host,
                roles=ViewerRoles.fixed(False, False, False),
                now=timezone.now(),
            )

    def test_member_standing_viewer_rule(self) -> None:
        set_org_feature(
            self.org, FeatureKey.CONTRIBUTIONS, enabled=True, actor=self.owner
        )
        self.org.members_private = True
        self.org.save()
        other = CustomUser.objects.create_user(username="ca_other", password="x")
        OrgUser.objects.create(user=other, organization=self.org)
        now = timezone.now()
        cases: list[tuple[CustomUser | AnonymousUser, bool]] = [
            (self.host, True),
            (self.owner, True),
            (other, False),
            (AnonymousUser(), False),
        ]
        for viewer, visible in cases:
            roles = standing.viewer_roles(self.org, viewer)
            block = CONTRIBUTION.member_standing(
                self.host_ou, viewer=viewer, roles=roles, now=now
            )
            self.assertEqual(block is not None, visible, viewer)
            found = standing.member_standing(self.host_ou, viewer=viewer, roles=roles)
            self.assertEqual("contribution" in found, visible, viewer)

    def test_promo_wrappers(self) -> None:
        send = PromoSend.objects.create(
            organization=self.org,
            event=self.event,
            recipient=self.host,
            sender=self.host,
            text="hi",
            earns_points=True,
        )
        self.assertFalse(has_promo_entry(send))
        self.assertIsNone(promo_points(send))
        ContributionEntry.objects.create(
            organization=self.org,
            org_user=self.host_ou,
            kind="promo_message",
            points=4,
            event=self.event,
            promo_send=send,
            occurred_at=timezone.now(),
        )
        self.assertTrue(has_promo_entry(send))
        self.assertEqual(promo_points(send), 4)
        self.assertEqual(revoke_promo_entry(send), 1)
        self.assertFalse(has_promo_entry(send))
        self.assertEqual(revoke_promo_entry(send), 0)

    def test_repoint_org_attribution(self) -> None:
        set_org_feature(
            self.org, FeatureKey.CONTRIBUTIONS, enabled=True, actor=self.host
        )
        template = PromoTemplate.objects.create(
            organization=self.org, name="Mine", body="x", created_by=self.host
        )
        self.assertEqual(repoint_org_attribution(self.host, self.owner), 2)
        feature = OrgFeature.objects.nocache().get(
            organization=self.org, feature=FeatureKey.CONTRIBUTIONS
        )
        self.assertEqual(feature.enabled_by_id, self.owner.pk)
        template.refresh_from_db()
        self.assertEqual(template.created_by_id, self.owner.pk)
