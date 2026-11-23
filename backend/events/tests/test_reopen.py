"""reopen_event and the guarded restart of a closed event's tournament (#405)."""

from unittest.mock import patch

from django.db.models import QuerySet
from rest_framework.test import APIClient

from app.models import CustomUser
from events import reopen as reopen_module
from events.completion import CloseResult, close_event
from events.constants import EventState
from events.models import Event
from events.reopen import ReopenNotPermitted, ReopenResult, reopen_event
from events.services import (
    create_tournament_for_event,
    resolve_or_create_org_user,
    restart_event_tournament,
)
from events.tests.test_completion import CompletionTestBase
from org.contributions.kinds import ContributionKind
from org.models import ContributionEntry, Organization, OrgLog
from tournament.models import Tournament


class ReopenTestBase(CompletionTestBase):
    @classmethod
    def setUpTestData(cls) -> None:
        super().setUpTestData()
        cls.org_staff = cls._make_user("reopen_org_staff")
        cls.org.staff.add(cls.org_staff)

    def setUp(self) -> None:
        super().setUp()
        self._staff()
        create_tournament_for_event(self.ev)
        self.ev.refresh_from_db()

    def _complete(self) -> None:
        close_event(
            self.ev, new_state=EventState.COMPLETED, source="admin", actor=self.admin
        )
        self.ev.refresh_from_db()

    def _auto_cancel(self) -> None:
        self._set_state(EventState.SIGNUPS_OPEN)
        close_event(self.ev, new_state=EventState.CANCELLED, source="auto")
        self.ev.refresh_from_db()

    def _staff_entries(self) -> QuerySet[ContributionEntry]:
        return self._entries().filter(
            kind__in=[ContributionKind.EVENT_HOST, ContributionKind.EVENT_HELPER]
        )

    def _other_entries(self) -> list[ContributionEntry]:
        org_user = self._staff_entries().first().org_user
        return [
            ContributionEntry.objects.create(
                org_user=org_user,
                organization=self.org,
                kind=kind,
                points=2,
                event=self.ev,
                occurred_at=self.start,
            )
            for kind in (ContributionKind.MANUAL, ContributionKind.PROMO_MESSAGE)
        ]

    def _reopen_logs(self) -> QuerySet[OrgLog]:
        return OrgLog.objects.filter(action="reopen_event")


class ReopenEventServiceTest(ReopenTestBase):
    def test_reopen_completed_revokes_staff_points(self) -> None:
        self._complete()
        self.assertEqual(self._staff_entries().count(), 3)
        result = reopen_event(self.ev, actor=self.admin)
        self.assertEqual(
            result,
            ReopenResult(
                reopened=True,
                state=EventState.SIGNUPS_OPEN,
                details={
                    "revoked": 3,
                    "attendance_reopened": 0,
                    "captain_reviews_voided": 0,
                    "leadership_revoked": 0,
                },
            ),
        )
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.state, EventState.SIGNUPS_OPEN)
        self.assertIsNone(self.ev.contributions_awarded_at)
        self.assertEqual(self._staff_entries().count(), 0)

    def test_reopen_auto_cancelled_revokes_staff_points(self) -> None:
        self._auto_cancel()
        self.assertEqual(self.ev.state, EventState.CANCELLED)
        self.assertEqual(self._staff_entries().count(), 3)
        result = reopen_event(self.ev, actor=self.admin)
        self.assertTrue(result.reopened)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.state, EventState.SIGNUPS_OPEN)
        self.assertIsNone(self.ev.contributions_awarded_at)
        self.assertEqual(self._staff_entries().count(), 0)

    def test_promo_and_manual_entries_survive(self) -> None:
        self._complete()
        kept = self._other_entries()
        reopen_event(self.ev, actor=self.admin)
        self.assertEqual(
            set(self._entries().values_list("pk", flat=True)), {e.pk for e in kept}
        )

    def test_other_org_entries_survive(self) -> None:
        self._complete()
        other_org = Organization.objects.create(
            name="Reopen Other Org", owner=self.unrelated_user
        )
        foreign = ContributionEntry.objects.create(
            org_user=resolve_or_create_org_user(self.host, other_org),
            organization=other_org,
            kind=ContributionKind.EVENT_HOST,
            points=10,
            event=self.ev,
            occurred_at=self.start,
        )
        reopen_event(self.ev, actor=self.admin)
        self.assertTrue(ContributionEntry.objects.filter(pk=foreign.pk).exists())

    def test_reopen_writes_org_log(self) -> None:
        self._complete()
        reopen_event(self.ev, actor=self.admin)
        entry = self._reopen_logs().get()
        self.assertEqual(entry.organization_id, self.org.pk)
        self.assertEqual(entry.actor_id, self.admin.pk)
        self.assertEqual(
            entry.details,
            {
                "event_id": self.ev.pk,
                "from": EventState.COMPLETED,
                "to": EventState.SIGNUPS_OPEN,
                "revoked": 3,
                "attendance_reopened": 0,
                "captain_reviews_voided": 0,
                "leadership_revoked": 0,
            },
        )

    def test_reopen_of_open_event_is_a_noop(self) -> None:
        result = reopen_event(self.ev, actor=self.admin)
        self.assertEqual(
            result,
            ReopenResult(reopened=False, state=EventState.IN_PROGRESS),
        )
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.state, EventState.IN_PROGRESS)
        self.assertFalse(self._reopen_logs().exists())

    def test_second_reopen_is_a_noop(self) -> None:
        self._complete()
        stale = Event.objects.nocache().get(pk=self.ev.pk)
        first = reopen_event(self.ev, actor=self.admin)
        second = reopen_event(stale, actor=self.admin)
        self.assertTrue(first.reopened)
        self.assertEqual(
            second,
            ReopenResult(reopened=False, state=EventState.SIGNUPS_OPEN),
        )
        self.assertEqual(self._reopen_logs().count(), 1)

    def test_close_after_reopen_awards_exactly_once(self) -> None:
        self._complete()
        reopen_event(self.ev, actor=self.admin)
        self._set_state(EventState.IN_PROGRESS)
        result = close_event(self.ev, new_state=EventState.COMPLETED, source="auto")
        self.assertTrue(result.closed)
        self.assertEqual(self._staff_entries().count(), 3)
        self.ev.refresh_from_db()
        self.assertIsNotNone(self.ev.contributions_awarded_at)

    def test_reopen_racing_reopen_revokes_once(self) -> None:
        self._complete()
        queryset_cls = type(Event.objects.nocache().all())
        original_update = queryset_cls.update
        raced: dict[str, object] = {}

        def racing_update(qs: QuerySet[Event], **kwargs: object) -> int:
            if kwargs.get("state") == EventState.SIGNUPS_OPEN and "inner" not in raced:
                raced["inner"] = None
                raced["inner"] = reopen_event(
                    Event.objects.nocache().get(pk=self.ev.pk), actor=self.admin
                )
            return original_update(qs, **kwargs)

        with patch.object(queryset_cls, "update", autospec=True) as update:
            update.side_effect = racing_update
            outer = reopen_event(self.ev, actor=self.admin)

        self.assertEqual(
            raced["inner"],
            ReopenResult(
                reopened=True,
                state=EventState.SIGNUPS_OPEN,
                details={
                    "revoked": 3,
                    "attendance_reopened": 0,
                    "captain_reviews_voided": 0,
                    "leadership_revoked": 0,
                },
            ),
        )
        self.assertFalse(outer.reopened)
        self.assertEqual(self._staff_entries().count(), 0)
        self.assertEqual(self._reopen_logs().count(), 1)

    def test_close_landing_before_reopen_reads_leaves_no_orphans(self) -> None:
        stale = Event.objects.nocache().get(pk=self.ev.pk)
        original_read = reopen_module._current_state
        raced: dict[str, object] = {}

        def racing_read(event: Event) -> str:
            if "inner" not in raced:
                raced["inner"] = None
                raced["inner"] = close_event(
                    Event.objects.nocache().get(pk=self.ev.pk),
                    new_state=EventState.COMPLETED,
                    source="auto",
                )
            return original_read(event)

        with patch.object(reopen_module, "_current_state", side_effect=racing_read):
            outer = reopen_event(stale, actor=self.admin)

        self.assertEqual(
            raced["inner"], CloseResult(closed=True, state=EventState.COMPLETED)
        )
        self.assertEqual(
            outer,
            ReopenResult(
                reopened=True,
                state=EventState.SIGNUPS_OPEN,
                details={
                    "revoked": 3,
                    "attendance_reopened": 0,
                    "captain_reviews_voided": 0,
                    "leadership_revoked": 0,
                },
            ),
        )
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.state, EventState.SIGNUPS_OPEN)
        self.assertIsNone(self.ev.contributions_awarded_at)
        self.assertEqual(self._staff_entries().count(), 0)

    def test_close_racing_after_reopen_is_skipped(self) -> None:
        self._complete()
        queryset_cls = type(Event.objects.nocache().all())
        original_update = queryset_cls.update
        raced: dict[str, object] = {}

        def racing_update(qs: QuerySet[Event], **kwargs: object) -> int:
            changed = original_update(qs, **kwargs)
            if kwargs.get("state") == EventState.SIGNUPS_OPEN and "inner" not in raced:
                raced["inner"] = None
                raced["inner"] = close_event(
                    Event.objects.nocache().get(pk=self.ev.pk),
                    new_state=EventState.COMPLETED,
                    source="auto",
                )
            return changed

        with patch.object(queryset_cls, "update", autospec=True) as update:
            update.side_effect = racing_update
            outer = reopen_event(self.ev, actor=self.admin)

        self.assertEqual(
            raced["inner"], CloseResult(closed=False, state=EventState.SIGNUPS_OPEN)
        )
        self.assertTrue(outer.reopened)
        self.assertEqual(self._staff_entries().count(), 0)


class RestartEventTournamentTest(ReopenTestBase):
    def test_restart_completed_with_reopen_permission(self) -> None:
        self._complete()
        old_tournament_id = self.ev.tournament_id
        restart_event_tournament(self.ev, actor=self.admin, can_reopen=True)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.state, EventState.SIGNUPS_OPEN)
        self.assertNotEqual(self.ev.tournament_id, old_tournament_id)
        self.assertIsNone(self.ev.contributions_awarded_at)
        self.assertEqual(self._staff_entries().count(), 0)
        self.assertEqual(self._reopen_logs().count(), 1)

    def test_restart_completed_with_past_tournament_starts_fresh(self) -> None:
        self._complete()
        old = self.ev.tournament
        Tournament.objects.filter(pk=old.pk).update(state="past")
        tournament = restart_event_tournament(
            self.ev, actor=self.admin, can_reopen=True
        )
        self.assertFalse(Tournament.objects.filter(pk=old.pk).exists())
        self.assertEqual(tournament.state, "future")
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.tournament_id, tournament.pk)
        self.assertEqual(self.ev.state, EventState.SIGNUPS_OPEN)

    def test_restart_completed_without_reopen_permission_is_refused(self) -> None:
        self._complete()
        old_tournament_id = self.ev.tournament_id
        with self.assertRaises(ReopenNotPermitted):
            restart_event_tournament(self.ev, actor=self.org_staff)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.state, EventState.COMPLETED)
        self.assertEqual(self.ev.tournament_id, old_tournament_id)
        self.assertEqual(self._staff_entries().count(), 3)

    def test_restart_in_progress_keeps_points_untouched(self) -> None:
        restart_event_tournament(self.ev, actor=self.org_staff)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.state, EventState.SIGNUPS_OPEN)
        self.assertFalse(self._reopen_logs().exists())

    def test_restart_roll_call_goes_back_to_signups(self) -> None:
        self._set_state(EventState.ROLL_CALL)
        restart_event_tournament(self.ev, actor=self.org_staff)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.state, EventState.SIGNUPS_OPEN)

    def test_restart_signups_open_stays_open(self) -> None:
        self._set_state(EventState.SIGNUPS_OPEN)
        old_tournament_id = self.ev.tournament_id
        restart_event_tournament(self.ev, actor=self.org_staff)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.state, EventState.SIGNUPS_OPEN)
        self.assertNotEqual(self.ev.tournament_id, old_tournament_id)

    def test_restart_racing_close_is_refused_and_keeps_tournament(self) -> None:
        old_tournament_id = self.ev.tournament_id
        queryset_cls = type(Event.objects.nocache().all())
        original_update = queryset_cls.update
        raced: dict[str, object] = {}

        def racing_update(qs: QuerySet[Event], **kwargs: object) -> int:
            if kwargs.get("state") == EventState.SIGNUPS_OPEN and "inner" not in raced:
                raced["inner"] = None
                raced["inner"] = close_event(
                    Event.objects.nocache().get(pk=self.ev.pk),
                    new_state=EventState.COMPLETED,
                    source="auto",
                )
            return original_update(qs, **kwargs)

        with (
            patch.object(queryset_cls, "update", autospec=True) as update,
            self.assertRaisesMessage(ValueError, "the event is now 'completed'"),
        ):
            update.side_effect = racing_update
            restart_event_tournament(self.ev, actor=self.org_staff)

        self.assertEqual(
            raced["inner"], CloseResult(closed=True, state=EventState.COMPLETED)
        )
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.tournament_id, old_tournament_id)
        self.assertFalse(self._reopen_logs().exists())


class RestartTournamentApiTest(ReopenTestBase):
    def _post(self, user: CustomUser) -> int:
        client = APIClient()
        client.force_authenticate(user)
        return client.post(f"/api/events/{self.ev.pk}/restart_tournament/").status_code

    def test_org_admin_can_restart_completed(self) -> None:
        self._complete()
        self.assertEqual(self._post(self.admin), 200)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.state, EventState.SIGNUPS_OPEN)
        self.assertEqual(self._staff_entries().count(), 0)

    def test_org_admin_can_restart_cancelled(self) -> None:
        self._auto_cancel()
        self.assertEqual(self._post(self.admin), 200)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.state, EventState.SIGNUPS_OPEN)
        self.assertEqual(self._staff_entries().count(), 0)

    def test_org_staff_cannot_restart_completed(self) -> None:
        self._complete()
        self.assertEqual(self._post(self.org_staff), 403)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.state, EventState.COMPLETED)
        self.assertEqual(self._staff_entries().count(), 3)

    def test_league_staff_cannot_restart_cancelled(self) -> None:
        Event.objects.filter(pk=self.ev.pk).update(tournament_league=self.league)
        self._auto_cancel()
        self.assertEqual(self._post(self.league_staff), 403)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.state, EventState.CANCELLED)

    def test_org_staff_can_restart_in_progress(self) -> None:
        self.assertEqual(self._post(self.org_staff), 200)
        self.ev.refresh_from_db()
        self.assertEqual(self.ev.state, EventState.SIGNUPS_OPEN)
