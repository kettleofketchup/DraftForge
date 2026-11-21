from collections.abc import Sequence

from events.constants import EventState, SignupStatus
from events.eligibility import store
from events.models import EventSignup
from events.tests.base import EventTestCase
from org.models import OrgUser
from org.standing import restamp


class RestampSlotTest(EventTestCase):
    def setUp(self) -> None:
        self.org_calls: list[int] = []
        self.member_calls: list[tuple[OrgUser, ...]] = []

    def org_fake(self, org_id: int) -> int:
        self.org_calls.append(org_id)
        return 0

    def member_fake(self, org_users: Sequence[OrgUser]) -> int:
        self.member_calls.append(tuple(org_users))
        return 0

    def org_user(self) -> OrgUser:
        return OrgUser.objects.get(user=self.make_user(), organization=self.org)

    def assert_store_registered(self) -> None:
        self.assertTrue(restamp.registered())
        self.assertIs(restamp._org_fn, store.refresh_org_eligibility)
        self.assertIs(restamp._member_fn, store.refresh_members_eligibility)

    def test_unregistered_raises(self) -> None:
        ou = self.org_user()
        with restamp.override(None, None):
            self.assertFalse(restamp.registered())
            with self.assertRaisesMessage(
                RuntimeError, "eligibility re-stamp is not registered"
            ):
                restamp.org_on_commit(1)
            with self.assertRaisesMessage(
                RuntimeError, "eligibility re-stamp is not registered"
            ):
                restamp.member_on_commit([ou])
        self.assert_store_registered()

    def test_override_restores_after_error(self) -> None:
        with self.assertRaises(ValueError), restamp.override(None, None):
            raise ValueError
        self.assert_store_registered()

    def test_org_on_commit_runs_after_commit(self) -> None:
        with restamp.override(self.org_fake, self.member_fake):
            with self.captureOnCommitCallbacks(execute=True):
                restamp.org_on_commit(7)
                self.assertEqual(self.org_calls, [])
            self.assertEqual(self.org_calls, [7])
        self.assert_store_registered()

    def test_member_on_commit_one_callback(self) -> None:
        first, second = self.org_user(), self.org_user()
        with restamp.override(self.org_fake, self.member_fake):
            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                restamp.member_on_commit([first, second, first])
            self.assertEqual(len(callbacks), 1)
            self.assertEqual(self.member_calls, [(first, second)])

            with self.captureOnCommitCallbacks(execute=True) as callbacks:
                restamp.member_on_commit([])
            self.assertEqual(callbacks, [])
        self.assertEqual(len(self.member_calls), 1)

    def test_store_registers_itself(self) -> None:
        self.assert_store_registered()

    def test_refresh_org_eligibility_skips_closed_events(self) -> None:
        user = self.make_user()
        open_signup = EventSignup.objects.create(
            event=self.make_event(),
            user=user,
            status=SignupStatus.PENDING_APPROVAL,
            unmet_requirements=["x"],
        )
        closed_signup = EventSignup.objects.create(
            event=self.make_event(state=EventState.COMPLETED),
            user=user,
            status=SignupStatus.PENDING_APPROVAL,
            unmet_requirements=["x"],
        )

        self.assertEqual(store.refresh_org_eligibility(self.org.pk), 1)

        open_signup.refresh_from_db()
        closed_signup.refresh_from_db()
        self.assertEqual(open_signup.unmet_requirements, [])
        self.assertEqual(closed_signup.unmet_requirements, ["x"])
