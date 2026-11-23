from collections.abc import Sequence
from datetime import timedelta
from unittest.mock import patch

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone as tz
from rest_framework.test import APIClient

from app.models import CustomUser
from events.admission import SignupRefused, ensure_self_serve
from events.completion import close_event
from events.constants import EventState, SignupStatus
from events.eligibility import evaluate_signup
from events.eligibility.checks.conduct import check_conduct, prime_conduct
from events.eligibility.checks.requirements import check_event_requirements
from events.eligibility.evaluate import CHECKS, PRIMERS, prime_checks
from events.eligibility.reasons import ReasonCode, Rule, Severity
from events.eligibility.store import (
    refresh_members_eligibility,
    refresh_org_eligibility,
    refresh_unmet_requirements,
)
from events.models import EventSignup
from events.services import staff_add_signup
from events.tests.actors import SYSTEM
from org.conduct.constants import Outcome
from org.conduct.gate import conduct_gate
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.models import OrgUser
from org.models_conduct import AttendanceOutcome, OrgConductSettings
from org.standing import restamp
from org.standing.cache import StandingCache
from org.tests.conduct_base import ConductTestCase

CODE = ReasonCode.CONDUCT_BELOW_THRESHOLD.value
SCORE_TABLE = AttendanceOutcome._meta.db_table
FINALIZE_RESTAMP_QUERIES = 10


def _score_queries(ctx: CaptureQueriesContext) -> list[str]:
    return [q["sql"] for q in ctx.captured_queries if SCORE_TABLE in q["sql"]]


@override_settings(CACHEOPS_ENABLED=False)
class ConductCheckTest(ConductTestCase):
    def setUp(self) -> None:
        self.unlock()

    def enable(self, **toggles: bool) -> OrgConductSettings:
        return OrgConductSettings.objects.create(organization=self.org, **toggles)

    def flagged(self) -> CustomUser:
        user = self.make_user()
        now = tz.now()
        for days in range(1, 5):
            self.outcome(
                user, outcome=Outcome.NO_SHOW, starts_at=now - timedelta(days=days)
            )
        return user

    def test_checks_order(self) -> None:
        self.assertEqual(CHECKS, (check_event_requirements, check_conduct))

    def test_block_is_blocking_for_self_serve(self) -> None:
        self.enable(block_enabled=True)
        result = evaluate_signup(self.make_event(), self.flagged())
        self.assertFalse(result.admissible)
        reason = result.blocking[0]
        self.assertEqual(reason.rule, Rule.CONDUCT_BLOCK)
        self.assertEqual(dict(reason.params), {"tier": "block"})

    def test_block_needs_approval_for_staff_placement(self) -> None:
        self.enable(block_enabled=True)
        result = evaluate_signup(
            self.make_event(), self.flagged(), for_staff_placement=True
        )
        self.assertTrue(result.admissible)
        self.assertEqual(result.approval[0].severity, Severity.NEEDS_APPROVAL)
        self.assertEqual(result.approval[0].rule, Rule.CONDUCT_BLOCK)

    def test_require_approval_reason(self) -> None:
        self.enable(require_approval_enabled=True)
        result = evaluate_signup(self.make_event(), self.flagged())
        self.assertTrue(result.admissible)
        self.assertEqual(result.approval[0].rule, Rule.CONDUCT_REQUIRE_APPROVAL)

    def test_params_never_carry_show_rate(self) -> None:
        self.enable(require_approval_enabled=True)
        result = evaluate_signup(self.make_event(), self.flagged())
        self.assertEqual(set(result.approval[0].params), {"tier"})

    def test_no_org_user_is_exempt_and_not_created(self) -> None:
        self.enable(block_enabled=True, enforce_on_new_members=True)
        user = self.make_user()
        OrgUser.objects.filter(user=user).delete()
        event = self.make_event()
        with CaptureQueriesContext(connection) as ctx:
            result = evaluate_signup(event, user)
        self.assertTrue(result.clean)
        self.assertEqual(_score_queries(ctx), [])
        self.assertFalse(OrgUser.objects.filter(user=user).exists())

    def test_primers(self) -> None:
        self.assertEqual(PRIMERS, (prime_conduct,))

    def test_prime_checks_scores_every_member_once(self) -> None:
        self.enable(require_approval_enabled=True)
        event = self.make_event()
        users = [self.flagged() for _ in range(3)]
        cache = StandingCache()
        now = tz.now()
        with CaptureQueriesContext(connection) as ctx:
            prime_checks(cache, self.org.pk, [u.pk for u in users], now=now)
            results = [
                evaluate_signup(event, u, now=now, standing_cache=cache) for u in users
            ]
        self.assertEqual(len(_score_queries(ctx)), 1)
        self.assertEqual([r.codes for r in results], [[CODE]] * 3)

    def test_locked_adds_only_gate_cost(self) -> None:
        self.enable(require_approval_enabled=True)
        user = self.flagged()
        self.signup(self.make_event(), user, SignupStatus.WAITLISTED)
        set_org_feature(self.org, FeatureKey.CONDUCT, enabled=False, actor=None)
        org_user = OrgUser.objects.get(user=user, organization=self.org)
        with CaptureQueriesContext(connection) as ctx:
            refresh_unmet_requirements(org_user)
        self.assertEqual(_score_queries(ctx), [])

    def test_refresh_members_eligibility_batches_per_org(self) -> None:
        self.enable(require_approval_enabled=True)
        event = self.make_event()
        users = [self.flagged() for _ in range(3)]
        for user in users:
            self.signup(event, user, SignupStatus.WAITLISTED)
        org_users = list(OrgUser.objects.filter(user__in=users))
        with (
            patch("org.conduct.eligibility.conduct_gate", wraps=conduct_gate) as built,
            CaptureQueriesContext(connection) as ctx,
        ):
            changed = refresh_members_eligibility(org_users)
        self.assertEqual(changed, 3)
        self.assertEqual(len(_score_queries(ctx)), 1)
        self.assertEqual(built.call_count, 1)

    def test_finalize_restamp_batched(self) -> None:
        self.enable(require_approval_enabled=True)
        done = self.make_event(
            state=EventState.IN_PROGRESS, scheduled_at=tz.now() - timedelta(hours=3)
        )
        other = self.make_event(max_players=0)
        users = [self.flagged() for _ in range(3)]
        for user in users:
            self.signup(done, user, SignupStatus.APPROVED)
            self.signup(other, user, SignupStatus.WAITLISTED)
        runs: list[tuple[int, int, int]] = []

        def counted(org_users: Sequence[OrgUser]) -> int:
            with (
                patch(
                    "org.conduct.eligibility.conduct_gate", wraps=conduct_gate
                ) as built,
                CaptureQueriesContext(connection) as ctx,
            ):
                refresh_members_eligibility(org_users)
            runs.append(
                (len(_score_queries(ctx)), built.call_count, len(ctx.captured_queries))
            )
            return 0

        with (
            restamp.override(refresh_org_eligibility, counted),
            self.captureOnCommitCallbacks(execute=True),
        ):
            close_event(
                done, new_state=EventState.COMPLETED, source="admin", actor=self.admin
            )
        self.assertEqual(runs, [(1, 1, FINALIZE_RESTAMP_QUERIES)])

    def test_eligibility_endpoint_reports_not_admissible(self) -> None:
        self.enable(block_enabled=True)
        user = self.flagged()
        event = self.make_event()
        client = APIClient()
        client.force_authenticate(user)
        response = client.get(f"/api/events/{event.pk}/eligibility/")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(response.data["admissible"])

    def test_self_serve_refusal_returns_reasons(self) -> None:
        self.enable(block_enabled=True)
        user = self.flagged()
        event = self.make_event()
        with self.assertRaises(SignupRefused) as caught:
            ensure_self_serve(event, user)
        self.assertEqual(caught.exception.result.codes, [CODE])
        client = APIClient()
        client.force_authenticate(user)
        response = client.post(
            f"/api/events/{event.pk}/signup/", {"intent": "rsvp"}, format="json"
        )
        self.assertEqual(response.status_code, 400, response.content)
        self.assertEqual(response.data["reasons"][0]["code"], CODE)

    def test_staff_add_lands_in_pending_approval(self) -> None:
        self.enable(block_enabled=True)
        event = self.make_event(auto_approve=True)
        signup = staff_add_signup(event, self.flagged(), actor=SYSTEM)
        self.assertEqual(signup.status, SignupStatus.PENDING_APPROVAL)
        self.assertEqual(signup.unmet_requirements, [CODE])

    def test_org_refresh_scores_once(self) -> None:
        self.enable(require_approval_enabled=True)
        event = self.make_event()
        for _ in range(3):
            self.signup(event, self.flagged(), SignupStatus.WAITLISTED)
        with CaptureQueriesContext(connection) as ctx:
            changed = refresh_org_eligibility(self.org.pk)
        self.assertEqual(changed, 3)
        score_queries = [
            q
            for q in ctx.captured_queries
            if AttendanceOutcome._meta.db_table in q["sql"]
        ]
        self.assertEqual(len(score_queries), 1)

    def test_org_refresh_skips_closed_events(self) -> None:
        self.enable(require_approval_enabled=True)
        done = self.make_event(state=EventState.COMPLETED)
        signup = self.signup(done, self.flagged(), SignupStatus.WAITLISTED)
        refresh_org_eligibility(self.org.pk)
        signup.refresh_from_db()
        self.assertEqual(signup.unmet_requirements, [])

    def test_feature_toggle_clears_stored_reasons(self) -> None:
        self.enable(require_approval_enabled=True)
        event = self.make_event()
        signup = self.signup(event, self.flagged(), SignupStatus.WAITLISTED)
        refresh_org_eligibility(self.org.pk)
        signup.refresh_from_db()
        self.assertEqual(signup.unmet_requirements, [CODE])
        set_org_feature(self.org, FeatureKey.CONDUCT, enabled=False, actor=None)
        refresh_org_eligibility(self.org.pk)
        signup = EventSignup.objects.nocache().get(pk=signup.pk)
        self.assertEqual(signup.unmet_requirements, [])
