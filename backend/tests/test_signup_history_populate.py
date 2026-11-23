from typing import Any
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIRequestFactory

from events.constants import ActorRole, SignupAction, SignupMeans, SignupStatus
from events.models import Event, EventSignup, SignupLedgerEntry
from org.models import OrgUser
from tests.data.signup_history import (
    SIGNUP_HISTORY_EVENT_NAME,
    SIGNUP_HISTORY_ORG,
    SIGNUP_HISTORY_REASON,
)
from tests.populate.signup_history import (
    populate_signup_history_data,
    signup_history_test_data,
)
from tests.test_signup_history import signup_history_data

DATA_KEYS: set[str] = {
    "org_pk",
    "event_pk",
    "staff_pk",
    "outsider_pk",
    "member_pks",
    "withdrawer_pk",
    "promoted_pk",
    "staff_added_pk",
    "long_nick_pk",
    "discord_button_pk",
    "reaction_pk",
}


class SignupHistoryPopulateTest(TestCase):
    def setUp(self) -> None:
        populate_signup_history_data(force=True)
        populate_signup_history_data(force=True)
        self.data: dict[str, Any] = signup_history_test_data()

    def _entries(self) -> list[SignupLedgerEntry]:
        return list(
            SignupLedgerEntry.objects.filter(event_id=self.data["event_pk"]).order_by(
                "pk"
            )
        )

    def _subjects(self, action: SignupAction) -> set[int]:
        return {e.subject_user_id for e in self._entries() if e.action == action}

    def test_single_fixture_event(self) -> None:
        events = Event.objects.nocache().filter(name=SIGNUP_HISTORY_EVENT_NAME)
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.get().pk, self.data["event_pk"])
        self.assertEqual(self.data["org_pk"], SIGNUP_HISTORY_ORG.pk)

    def test_required_actions(self) -> None:
        actions = {e.action for e in self._entries()}
        self.assertTrue(
            {
                SignupAction.WITHDREW,
                SignupAction.RESIGNED_UP,
                SignupAction.STAFF_ADDED,
                SignupAction.PROMOTED,
            }
            <= actions,
            actions,
        )
        staff_added = [
            e for e in self._entries() if e.action == SignupAction.STAFF_ADDED
        ]
        self.assertEqual(len(staff_added), 1)
        self.assertEqual(staff_added[0].reason, SIGNUP_HISTORY_REASON)
        self.assertEqual(staff_added[0].actor_role, ActorRole.STAFF)
        promoted = [e for e in self._entries() if e.action == SignupAction.PROMOTED]
        self.assertTrue(promoted)
        self.assertTrue(all(e.caused_by_id is not None for e in promoted))

    def test_means_and_roles(self) -> None:
        means = {e.means for e in self._entries()}
        self.assertTrue(
            {
                SignupMeans.WEB,
                SignupMeans.DISCORD_BUTTON,
                SignupMeans.DISCORD_REACTION,
                SignupMeans.SYSTEM,
            }
            <= means,
            means,
        )
        self.assertIn(ActorRole.STAFF, {e.actor_role for e in self._entries()})

    def test_data_keys(self) -> None:
        self.assertEqual(set(self.data), DATA_KEYS)
        self.assertEqual(len(self.data["member_pks"]), 5)

    def test_named_roles(self) -> None:
        d = self.data
        self.assertIn(d["withdrawer_pk"], self._subjects(SignupAction.WITHDREW))
        self.assertIn(d["withdrawer_pk"], self._subjects(SignupAction.RESIGNED_UP))
        self.assertIn(d["promoted_pk"], self._subjects(SignupAction.PROMOTED))
        self.assertEqual(
            self._subjects(SignupAction.STAFF_ADDED), {d["staff_added_pk"]}
        )
        by_means: dict[str, set[int]] = {}
        for e in self._entries():
            by_means.setdefault(e.means, set()).add(e.subject_user_id)
        self.assertIn(d["discord_button_pk"], by_means[SignupMeans.DISCORD_BUTTON])
        self.assertIn(d["reaction_pk"], by_means[SignupMeans.DISCORD_REACTION])
        long_nick = next(
            e for e in self._entries() if e.subject_user_id == d["long_nick_pk"]
        )
        self.assertGreaterEqual(len(long_nick.subject_user.nickname), 40)
        self.assertNotIn(" ", long_nick.subject_user.nickname)
        for pk in d["member_pks"]:
            self.assertTrue(
                OrgUser.objects.filter(
                    organization_id=SIGNUP_HISTORY_ORG.pk, user_id=pk
                ).exists()
            )

    def test_final_statuses(self) -> None:
        d = self.data
        statuses = dict(
            EventSignup.objects.nocache()
            .filter(event_id=d["event_pk"])
            .values_list("user_id", "status")
        )
        self.assertEqual(
            statuses,
            {
                d["discord_button_pk"]: SignupStatus.RSVP,
                d["promoted_pk"]: SignupStatus.RSVP,
                d["withdrawer_pk"]: SignupStatus.WAITLISTED,
                d["long_nick_pk"]: SignupStatus.WAITLISTED,
                d["staff_added_pk"]: SignupStatus.WAITLISTED,
            },
        )

    def test_outsider_not_member(self) -> None:
        self.assertFalse(
            OrgUser.objects.filter(
                organization_id=SIGNUP_HISTORY_ORG.pk, user_id=self.data["outsider_pk"]
            ).exists()
        )

    def test_force_leaves_no_orphan_ledger_rows(self) -> None:
        live = set(Event.objects.nocache().values_list("pk", flat=True))
        orphans = SignupLedgerEntry.objects.filter(
            organization_id=SIGNUP_HISTORY_ORG.pk
        ).exclude(event_id__in=live)
        self.assertFalse(orphans.exists())

    @patch("tests.test_signup_history.isTestEnvironment", return_value=True)
    def test_data_endpoint(self, _env: Any) -> None:
        request = APIRequestFactory().get("/api/tests/signup-history/data/")
        response = signup_history_data(request)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, self.data)
