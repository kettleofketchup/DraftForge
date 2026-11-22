from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.db import IntegrityError, connection, transaction
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone as tz
from rest_framework.test import APIClient

from app.discord_accounts import merge_discord_accounts
from app.models import CustomUser, ProfileClaimRequest
from events.constants import EventState
from events.models import Event
from events.reopen import reopen_event
from events.services import teardown_event
from org.conduct.constants import Outcome, OutcomeSource
from org.contributions.adapter import CONTRIBUTION
from org.contributions.services import award_entry
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.leadership.adapter import LEADERSHIP
from org.models import (
    AttendanceOutcome,
    CaptainReview,
    ContributionEntry,
    EventCaptain,
    OrgLeadershipSettings,
    OrgLog,
    OrgUser,
)
from org.standing import api as standing
from org.standing.periods import parse_period
from org.tests.leadership_base import LeadershipTestCase

CLOSE_KEYS = ("captains_snapshotted", "leadership_awarded")
CLOSE_LOG_KEYS = ("captain_reviews_voided", "leadership_revoked")


def pool(snapshot: EventCaptain) -> set[int]:
    return set(snapshot.teammates.values_list("user_id", flat=True))


def leadership_rows(user: CustomUser) -> int:
    return (
        ContributionEntry.objects.nocache()
        .filter(org_user__user=user, track="leadership")
        .count()
    )


class CloseHookTest(LeadershipTestCase):
    def close_hook(self, *, cancelled: bool = False) -> standing.HookResult:
        Event.objects.filter(pk=self.event.pk).update(state=EventState.COMPLETED)
        self.event.refresh_from_db()
        with transaction.atomic():
            return standing.on_event_closed(
                self.event, cancelled=cancelled, source="admin", actor=self.admin
            )

    def test_close_hook_dispatch(self) -> None:
        out = self.close_hook().by_track["leadership"]
        self.assertEqual(
            out.orglog, {"captains_snapshotted": 2, "leadership_awarded": 4}
        )
        self.assertEqual(
            out.log, {"captain_reviews_voided": 0, "leadership_revoked": 0}
        )

    def test_close_hook_locked_writes_nothing(self) -> None:
        set_org_feature(self.org, FeatureKey.LEADERSHIP, enabled=False, actor=None)
        out = self.close_hook().by_track["leadership"]
        self.assertEqual(tuple(out.orglog), CLOSE_KEYS)
        self.assertEqual(set(out.orglog.values()), {0})
        self.assertEqual(tuple(out.log), CLOSE_LOG_KEYS)
        self.assertFalse(EventCaptain.objects.exists())
        self.assertFalse(ContributionEntry.objects.filter(track="leadership").exists())

    def test_cancel_after_close_reports_voids(self) -> None:
        self.close_hook()
        self.review(self.mates_a[0], self.cap_a)
        out = self.close_hook(cancelled=True).by_track["leadership"]
        self.assertEqual(
            out.orglog, {"captains_snapshotted": 0, "leadership_awarded": 0}
        )
        self.assertEqual(
            out.log, {"captain_reviews_voided": 1, "leadership_revoked": 4}
        )

    def test_reopen_and_cancel_hooks_run_when_locked(self) -> None:
        self.close_hook()
        self.review(self.mates_a[0], self.cap_a)
        set_org_feature(self.org, FeatureKey.LEADERSHIP, enabled=False, actor=None)
        with transaction.atomic():
            result = standing.on_event_reopened(self.event, actor=self.admin)
        details = result.orglog_details()
        self.assertEqual(details["captain_reviews_voided"], 1)
        self.assertEqual(details["leadership_revoked"], 4)
        self.assertFalse(EventCaptain.objects.filter(voided_at__isnull=True).exists())
        self.assertEqual(
            CaptainReview.objects.get().void_kind,
            "lifecycle",
        )


class RealCallSiteTest(LeadershipTestCase):
    def test_complete_and_reopen_log_leadership_keys(self) -> None:
        self.close()
        details = OrgLog.objects.get(action="complete_event").details
        self.assertEqual(details["captains_snapshotted"], 2)
        self.assertEqual(details["leadership_awarded"], 4)
        self.assertEqual(EventCaptain.objects.count(), 2)
        self.review(self.mates_a[0], self.cap_a)
        self.event.refresh_from_db()
        self.assertTrue(reopen_event(self.event, actor=self.admin).reopened)
        details = OrgLog.objects.get(action="reopen_event").details
        self.assertEqual(details["captain_reviews_voided"], 1)
        self.assertEqual(details["leadership_revoked"], 4)
        self.assertEqual(leadership_rows(self.cap_a), 0)

    def test_admin_cancel_writes_nothing(self) -> None:
        self.close(state=EventState.CANCELLED)
        self.assertFalse(EventCaptain.objects.exists())

    def test_teardown_removes_rows(self) -> None:
        self.close()
        self.review(self.mates_a[0], self.cap_a)
        self.event.refresh_from_db()
        teardown_event(self.event, actor=self.admin)
        self.assertFalse(EventCaptain.objects.exists())
        self.assertFalse(CaptainReview.objects.exists())
        self.assertFalse(ContributionEntry.objects.filter(track="leadership").exists())

    def test_close_event_runs_conduct_before_leadership(self) -> None:
        set_org_feature(self.org, FeatureKey.CONDUCT, enabled=True, actor=None)
        excused = self.mates_a[2]
        self.outcome(
            excused,
            event=self.event,
            outcome=Outcome.EXCUSED,
            source=OutcomeSource.STAFF,
            finalized=False,
            reason="away",
        )
        self.close()
        attended = set(
            AttendanceOutcome.objects.filter(
                event=self.event, outcome=Outcome.ATTENDED
            ).values_list("org_user__user_id", flat=True)
        )
        self.assertEqual(
            pool(self.snapshot(self.cap_a)), {u.pk for u in self.mates_a[:2]}
        )
        self.assertEqual(pool(self.snapshot(self.cap_b)), {u.pk for u in self.mates_b})
        self.assertTrue({u.pk for u in [*self.mates_a[:2], *self.mates_b]} <= attended)
        self.assertNotIn(excused.pk, attended)


class MergeSiteTest(LeadershipTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.close()
        self.superuser = CustomUser.objects.create_superuser(
            username="ld_claim_admin", password="x"
        )

    def approve_claim(self, keep: CustomUser, drop: CustomUser) -> None:
        claim = ProfileClaimRequest.objects.create(
            claimer=keep,
            target_user=drop,
            organization=self.org,
            status=ProfileClaimRequest.Status.PENDING,
        )
        client = APIClient()
        client.force_authenticate(self.superuser)
        res = client.post(reverse("claim-request-approve", args=[claim.pk]))
        self.assertEqual(res.status_code, 200, res.content)
        self.assertFalse(CustomUser.objects.filter(pk=drop.pk).exists())

    def test_claim_merge_captain_collision(self) -> None:
        self.review(self.mates_b[0], self.cap_b, 4)
        self.approve_claim(self.cap_a, self.cap_b)
        self.assertEqual(EventCaptain.objects.filter(event=self.event).count(), 1)
        self.assertEqual(
            CaptainReview.objects.get().event_captain.captain.user, self.cap_a
        )

    def test_discord_merge_rater_collision(self) -> None:
        self.review(self.mates_a[0], self.cap_a, 2)
        self.review(self.mates_a[1], self.cap_a, 5)
        try:
            merge_discord_accounts(keep=self.mates_a[1], drop=self.mates_a[0])
        except IntegrityError as exc:
            self.fail(f"merge raised {exc}")
        review = CaptainReview.objects.get()
        self.assertEqual(review.rater.user, self.mates_a[1])

    def test_claim_merge_both_teammates_in_one_pool(self) -> None:
        self.approve_claim(self.mates_a[1], self.mates_a[0])
        keep = OrgUser.objects.get(user=self.mates_a[1], organization=self.org)
        mates = list(self.snapshot(self.cap_a).teammates.values_list("pk", flat=True))
        self.assertEqual(mates.count(keep.pk), 1)
        self.assertEqual(len(mates), 2)


class UserDeleteTest(LeadershipTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.close()
        award_entry(
            org=self.org,
            user=self.cap_a,
            kind="manual",
            points=3,
            reason="help",
            occurred_at=tz.now(),
        )
        self.contribution = (
            ContributionEntry.objects.filter(org_user__user=self.cap_a)
            .exclude(track="leadership")
            .count()
        )
        self.leadership = leadership_rows(self.cap_a)
        self.superuser = CustomUser.objects.create_superuser(
            username="ld_delete_admin", password="x"
        )

    def test_api_delete_logs_both_tracks(self) -> None:
        client = APIClient()
        client.force_authenticate(self.superuser)
        res = client.delete(reverse("users-detail", args=[self.cap_a.pk]))
        self.assertEqual(res.status_code, 204, res.content)
        contrib = OrgLog.objects.get(action="delete_user_contributions")
        lead = OrgLog.objects.get(action="delete_user_leadership")
        self.assertEqual(contrib.details["count"], self.contribution)
        self.assertEqual(lead.details["count"], self.leadership)

    def test_admin_confirmation_counts_every_ledger_row(self) -> None:
        self.client.force_login(self.superuser)
        res = self.client.get(
            reverse("admin:app_customuser_delete", args=[self.cap_a.pk])
        )
        self.assertEqual(res.status_code, 200)
        self.assertNotContains(res, "protected related objects")
        counts = dict(res.context["model_count"])
        self.assertEqual(
            counts[str(ContributionEntry._meta.verbose_name_plural)],
            self.contribution + self.leadership,
        )

    def test_each_track_reports_only_its_own_blockers(self) -> None:
        for track, expected in (
            (CONTRIBUTION, self.contribution),
            (LEADERSHIP, self.leadership),
        ):
            with self.subTest(track=track.key):
                rows = track.deletion_blockers([self.cap_a.pk])
                self.assertEqual(sum(qs.count() for qs in rows), expected)
                self.assertEqual(
                    {t for qs in rows for t in qs.values_list("track", flat=True)},
                    {track.key},
                )


class EndpointTest(LeadershipTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.close()
        for mate in self.mates_a:
            self.review(mate, self.cap_a, 5)

    def board(
        self, client: APIClient, metric: str = "rating"
    ) -> tuple[int, dict | None]:
        res = client.get(
            f"/api/organizations/{self.org.pk}/standing/leadership/leaderboard/"
            f"?metric={metric}"
        )
        return res.status_code, res.json() if res.content else None

    def set_public(self, public: bool) -> None:
        OrgLeadershipSettings.objects.update_or_create(
            organization=self.org,
            defaults={"leaderboard_public": public, "ranked_min_reviews": 2},
        )

    def test_generic_endpoints_list_leadership(self) -> None:
        set_org_feature(self.org, FeatureKey.CONTRIBUTIONS, enabled=True, actor=None)
        set_org_feature(self.org, FeatureKey.CONDUCT, enabled=True, actor=None)
        res = self.client_for(self.admin).get(
            f"/api/organizations/{self.org.pk}/standing/tracks/"
        )
        tracks = res.json()["tracks"]
        self.assertEqual(
            [t["key"] for t in tracks], ["contribution", "conduct", "leadership"]
        )
        metrics = [m["key"] for m in tracks[2]["metrics"]]
        self.assertEqual(metrics[:2], ["rating", "points"])
        self.assertIn("rating.communication", metrics)

    def test_anonymous_denied_on_private_board(self) -> None:
        self.set_public(False)
        status, body = self.board(APIClient())
        self.assertIn(status, (401, 403))
        self.assertIn("credentials were not provided", body["detail"])

    def test_anonymous_public_board_hides_rows(self) -> None:
        self.set_public(True)
        self.expire_window()
        status, body = self.board(APIClient())
        self.assertEqual(status, 200)
        self.assertEqual(body["rows"], [])
        self.assertIsNone(body["own_row"])

    def test_private_board_member_sees_only_own_row(self) -> None:
        self.set_public(False)
        self.expire_window()
        status, body = self.board(self.client_for(self.cap_a))
        self.assertEqual(status, 200)
        self.assertEqual(body["rows"], [])
        self.assertFalse(body["rows_visible"])
        self.assertEqual(body["own_row"]["member"]["user_pk"], self.cap_a.pk)

    def test_member_without_rating_gets_new_own_row(self) -> None:
        self.set_public(False)
        self.expire_window()
        for metric in ("rating", "points"):
            status, body = self.board(self.client_for(self.mates_b[0]), metric)
            self.assertEqual(status, 200)
            own = body["own_row"]
            self.assertEqual(own["member"]["user_pk"], self.mates_b[0].pk)
            self.assertIsNone(own["value"])
            self.assertEqual(own["status"], "new")

    def test_public_board_private_member_list_hides_rows(self) -> None:
        self.set_public(True)
        self.expire_window()
        self.org.members_private = True
        self.org.save(update_fields=["members_private"])
        status, body = self.board(self.client_for(self.mates_b[0]))
        self.assertEqual(status, 200)
        self.assertEqual(body["rows"], [])

    def test_staff_sees_rows(self) -> None:
        self.expire_window()
        status, body = self.board(self.client_for(self.admin))
        self.assertEqual(status, 200)
        self.assertEqual(
            [r["member"]["user_pk"] for r in body["rows"]], [self.cap_a.pk]
        )

    def test_locked_feature(self) -> None:
        set_org_feature(self.org, FeatureKey.LEADERSHIP, enabled=False, actor=None)
        status, body = self.board(self.client_for(self.admin))
        self.assertEqual(status, 403)
        self.assertEqual(body["code"], "feature_locked")

    def test_bogus_trait_metric(self) -> None:
        status, _ = self.board(self.client_for(self.admin), "rating.bogus")
        self.assertEqual(status, 400)

    def test_points_metric_hides_unreleased_captain_rating(self) -> None:
        period = parse_period(self.org, None)
        before = standing.leaderboard(
            self.org, "leadership", "points", period, viewer=self.admin
        )
        totals = {r.member["user_pk"]: r.value for r in before.rows}
        self.assertEqual(totals[self.cap_a.pk], 5 + 10)
        self.assertEqual(before.total, 5 + 10 + 5 + 6)
        self.expire_window()
        after = standing.leaderboard(
            self.org, "leadership", "points", period, viewer=self.admin
        )
        totals = {r.member["user_pk"]: r.value for r in after.rows}
        self.assertEqual(totals[self.cap_a.pk], 5 + 10 + 10)
        self.assertEqual(after.total, 5 + 10 + 10 + 5 + 6)

    def test_anonymous_api_leaderboard_denied(self) -> None:
        self.set_public(False)
        with self.assertRaises(standing.AccessDenied):
            standing.leaderboard(
                self.org,
                "leadership",
                "rating",
                parse_period(self.org, None),
                viewer=AnonymousUser(),
            )


@override_settings(CACHEOPS_ENABLED=False)
class LeaderboardBudgetTest(LeadershipTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.close()

    def add_captains(self, n: int) -> None:
        event, tournament = self.make_event(f"Budget {n}")
        for i in range(n):
            cap = self.make_user(f"ld_bcap{n}_{i}")
            mates = [self.make_user(f"ld_bmate{n}_{i}_{j}") for j in range(2)]
            self.make_team(f"B{n}{i}", cap, mates, tournament=tournament)
            for user in [cap, *mates]:
                self.admit(user, event)
        self.close(event)
        for snap in EventCaptain.objects.filter(event=event):
            for mate in snap.teammates.all():
                self.review(mate.user, snap.captain.user, 4, event=event)
        EventCaptain.objects.update(window_closes_at=tz.now() - timedelta(minutes=1))

    def measure(self, metric: str) -> int:
        client = self.client_for(self.admin)
        with CaptureQueriesContext(connection) as ctx:
            res = client.get(
                f"/api/organizations/{self.org.pk}/standing/leadership/leaderboard/"
                f"?metric={metric}"
            )
        self.assertEqual(res.status_code, 200, res.content)
        return len(ctx.captured_queries)

    def test_leaderboard_budget(self) -> None:
        self.add_captains(3)
        small = {m: self.measure(m) for m in ("rating", "points")}
        self.add_captains(9)
        self.assertEqual({m: self.measure(m) for m in ("rating", "points")}, small)
