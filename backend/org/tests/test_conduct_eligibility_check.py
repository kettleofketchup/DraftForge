from datetime import timedelta

from django.db import connection
from django.test import override_settings
from django.test.utils import CaptureQueriesContext
from django.utils import timezone as tz
from rest_framework.test import APIClient

from app.models import CustomUser
from events.admission import SignupRefused, ensure_self_serve
from events.constants import EventState, SignupStatus
from events.eligibility import evaluate_signup
from events.eligibility.checks.conduct import check_conduct
from events.eligibility.checks.requirements import check_event_requirements
from events.eligibility.evaluate import CHECKS
from events.eligibility.reasons import ReasonCode, Rule, Severity
from events.eligibility.store import refresh_org_eligibility
from events.models import EventSignup
from events.services import staff_add_signup
from org.conduct.constants import Outcome
from org.feature_keys import FeatureKey
from org.features import set_org_feature
from org.models import OrgUser
from org.models_conduct import AttendanceOutcome, OrgConductSettings
from org.tests.conduct_base import ConductTestCase

CODE = ReasonCode.CONDUCT_BELOW_THRESHOLD.value


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
        result = evaluate_signup(self.make_event(), user)
        self.assertTrue(result.clean)
        self.assertFalse(OrgUser.objects.filter(user=user).exists())

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
        signup = staff_add_signup(event, self.flagged())
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
