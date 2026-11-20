from collections.abc import Callable
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Literal
from unittest.mock import patch

from django.db import connection, transaction
from django.test import SimpleTestCase, override_settings
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone as tz
from rest_framework.test import APIClient

from app.models import CustomUser, GameType, Tournament
from discordbot.models import DiscordMessageLog
from events.admission import ensure_self_serve
from events.constants import EventState, SignupStatus
from events.discord.handlers import handle_signup_button
from events.discord.reactions import handle_reaction_signup
from events.eligibility import Unmet, refresh_unmet_requirements
from events.models import Event, EventSignup
from events.services import (
    _promote_from_waitlist,
    cancel_signup,
    create_tentative_signup,
    process_rsvp,
    staff_add_signup,
)
from org.conduct.constants import CONDUCT_BLOCK_MESSAGE, Outcome, Tier
from org.conduct.enforcement import (
    defer_back_of_line,
    is_deferred,
    tier_for,
    tier_for_score,
    tiers_for,
)
from org.conduct.finalize import finalize_event_outcomes
from org.conduct.gate import GATE_OFF, ConductGate
from org.conduct.scoring import MemberScore
from org.conduct.services import set_outcomes, update_conduct_settings
from org.models_conduct import AttendanceOutcome, OrgConductSettings
from org.models_profiles import PlayerDeadlockProfile
from org.tests.conduct_base import ConductTestCase

DISCORD_ID = "300000000000000077"
CODE = Unmet.CONDUCT_BELOW_THRESHOLD.value


def _score(rate: float, status: Literal["new", "scored"] = "scored") -> MemberScore:
    return MemberScore(
        show_rate=rate, status=status, counted_events=5, weighted_events=5.0
    )


@override_settings(CACHEOPS_ENABLED=False)
class TierTest(ConductTestCase):
    def all_modes(self, **overrides: object) -> OrgConductSettings:
        fields: dict[str, object] = {
            "organization": self.org,
            "back_of_line_enabled": True,
            "back_of_line_below": Decimal("0.75"),
            "require_approval_enabled": True,
            "require_approval_below": Decimal("0.65"),
            "block_enabled": True,
            "block_below": Decimal("0.40"),
        }
        fields.update(overrides)
        return OrgConductSettings(**fields)

    def active_gate(self, settings: OrgConductSettings) -> ConductGate:
        return ConductGate(
            org_id=self.org.pk,
            feature_on=True,
            settings=settings,
            enforcement_active=True,
        )

    def test_off_gate_zero_queries(self) -> None:
        with self.assertNumQueries(0):
            self.assertEqual(tier_for(GATE_OFF, self.user), Tier.OK)
            self.assertEqual(
                tiers_for(GATE_OFF, [self.user, self.admin]),
                {self.user.pk: Tier.OK, self.admin.pk: Tier.OK},
            )

    def test_feature_on_without_modes_zero_queries(self) -> None:
        gate = ConductGate(
            org_id=self.org.pk,
            feature_on=True,
            settings=OrgConductSettings(organization=self.org),
            enforcement_active=False,
        )
        with self.assertNumQueries(0):
            self.assertEqual(tier_for(gate, self.user), Tier.OK)

    def test_strictest_tier_wins(self) -> None:
        settings = self.all_modes()
        self.assertEqual(tier_for_score(_score(0.3), settings), Tier.BLOCK)
        self.assertEqual(tier_for_score(_score(0.5), settings), Tier.REQUIRE_APPROVAL)
        self.assertEqual(tier_for_score(_score(0.7), settings), Tier.BACK_OF_LINE)
        self.assertEqual(tier_for_score(_score(0.8), settings), Tier.OK)

    def test_threshold_is_strictly_below(self) -> None:
        settings = self.all_modes()
        self.assertEqual(tier_for_score(_score(0.75), settings), Tier.OK)
        self.assertEqual(tier_for_score(_score(0.40), settings), Tier.REQUIRE_APPROVAL)

    def test_disabled_modes_skipped(self) -> None:
        settings = self.all_modes(block_enabled=False)
        self.assertEqual(tier_for_score(_score(0.3), settings), Tier.REQUIRE_APPROVAL)
        settings = self.all_modes(block_enabled=False, require_approval_enabled=False)
        self.assertEqual(tier_for_score(_score(0.3), settings), Tier.BACK_OF_LINE)

    def test_new_member_exempt_unless_configured(self) -> None:
        settings = self.all_modes()
        self.assertEqual(tier_for_score(_score(0.1, "new"), settings), Tier.OK)
        settings = self.all_modes(enforce_on_new_members=True)
        self.assertEqual(tier_for_score(_score(0.1, "new"), settings), Tier.BLOCK)

    def test_deferral_uses_back_of_line_threshold(self) -> None:
        settings = self.all_modes(
            back_of_line_below=Decimal("0.50"),
            require_approval_below=Decimal("0.65"),
            block_enabled=False,
        )

        self.assertEqual(tier_for_score(_score(0.60), settings), Tier.REQUIRE_APPROVAL)
        self.assertFalse(is_deferred(_score(0.60), settings))
        self.assertTrue(is_deferred(_score(0.45), settings))
        self.assertFalse(is_deferred(_score(0.45, "new"), settings))
        self.assertFalse(
            is_deferred(_score(0.45), self.all_modes(back_of_line_enabled=False))
        )

    def test_tier_for_scores_member(self) -> None:
        now = tz.now()
        for days in (1, 2, 3, 4):
            self.outcome(
                self.user,
                outcome=Outcome.NO_SHOW,
                starts_at=now - timedelta(days=days),
            )
        gate = self.active_gate(self.all_modes())

        with self.assertNumQueries(1):
            self.assertEqual(tier_for(gate, self.user), Tier.BLOCK)

    def test_tiers_for_single_query(self) -> None:
        now = tz.now()
        for days in (1, 2, 3, 4):
            self.outcome(
                self.user,
                outcome=Outcome.NO_SHOW,
                starts_at=now - timedelta(days=days),
            )
            self.outcome(self.admin, starts_at=now - timedelta(days=days))
        gate = self.active_gate(self.all_modes())

        with self.assertNumQueries(1):
            tiers = tiers_for(gate, [self.user, self.admin, self.league_staff])

        self.assertEqual(
            tiers,
            {
                self.user.pk: Tier.BLOCK,
                self.admin.pk: Tier.OK,
                self.league_staff.pk: Tier.OK,
            },
        )


@dataclass(frozen=True)
class _Candidate:
    name: str
    user_id: int


class DeferTest(SimpleTestCase):
    def test_stable_partition(self) -> None:
        a, b, c, d = (_Candidate(n, i) for i, n in enumerate("abcd", start=1))

        self.assertEqual(defer_back_of_line([a, b, c, d], {2, 4}), [a, c, b, d])

    def test_unknown_ids_ignored(self) -> None:
        a, b = _Candidate("a", 1), _Candidate("b", 2)

        self.assertEqual(defer_back_of_line([a, b], {9}), [a, b])

    def test_defer_empty(self) -> None:
        self.assertEqual(defer_back_of_line([], set()), [])


class EnforcementHooksTest(ConductTestCase):
    def setUp(self) -> None:
        self.unlock()

    def enable(self, **toggles: bool) -> OrgConductSettings:
        return OrgConductSettings.objects.create(organization=self.org, **toggles)

    def no_shows(self, user: CustomUser, count: int) -> None:
        now = tz.now()
        for days in range(1, count + 1):
            self.outcome(
                user, outcome=Outcome.NO_SHOW, starts_at=now - timedelta(days=days)
            )

    def blocked_member(self) -> CustomUser:
        self.enable(block_enabled=True)
        user = self.make_user()
        self.no_shows(user, 4)
        return user

    def test_block_web_signup_400(self) -> None:
        user = self.blocked_member()
        event = self.make_event()
        client = APIClient()
        client.force_authenticate(user)

        resp = client.post(
            f"/api/events/{event.pk}/signup/", {"intent": "rsvp"}, format="json"
        )

        self.assertEqual(resp.status_code, 400, resp.content)
        body = resp.json()
        self.assertEqual(body["error"], CONDUCT_BLOCK_MESSAGE)
        self.assertEqual([r["code"] for r in body["reasons"]], [CODE])
        self.assertFalse(EventSignup.objects.filter(event=event).exists())

    def test_block_discord_button(self) -> None:
        user = self.blocked_member()
        user.discordId = DISCORD_ID
        user.save()
        PlayerDeadlockProfile.objects.create(
            org_user=self.org_user(user), rank="Ascendant"
        )
        event = self.make_event(game_type=GameType.DEADLOCK)

        result = handle_signup_button(event.pk, DISCORD_ID, user.username)

        self.assertEqual(result, {"action": "error", "message": CONDUCT_BLOCK_MESSAGE})
        self.assertFalse(EventSignup.objects.filter(event=event).exists())

    def test_block_reaction_add(self) -> None:
        user = self.blocked_member()
        user.discordId = DISCORD_ID
        user.save()
        event = self.make_event()
        DiscordMessageLog.objects.create(
            channel_id="1",
            embed_data={"title": "Test"},
            source="event_announcement",
            source_id=event.pk,
            discord_message_id="555000777",
            success=True,
        )

        success, detail = handle_reaction_signup("555000777", DISCORD_ID)

        self.assertFalse(success)
        self.assertEqual(detail, CONDUCT_BLOCK_MESSAGE)
        self.assertFalse(EventSignup.objects.filter(event=event).exists())

    def test_block_tentative(self) -> None:
        user = self.blocked_member()
        event = self.make_event()

        with self.assertRaisesMessage(ValueError, CONDUCT_BLOCK_MESSAGE):
            create_tentative_signup(event, user)

        self.assertFalse(EventSignup.objects.filter(event=event).exists())

    def test_block_spares_clean_member(self) -> None:
        self.enable(block_enabled=True)
        event = self.make_event()

        signup = process_rsvp(event, self.make_user())

        self.assertEqual(signup.status, SignupStatus.APPROVED)
        self.assertEqual(signup.unmet_requirements, [])

    def test_staff_add_bypasses_block(self) -> None:
        user = self.blocked_member()
        event = self.make_event()

        signup = staff_add_signup(event, user)

        self.assertEqual(signup.unmet_requirements, [CODE])
        self.assertEqual(signup.status, SignupStatus.PENDING_APPROVAL)

    def test_require_approval_pending_on_auto_approve(self) -> None:
        self.enable(require_approval_enabled=True)
        flagged = self.make_user()
        self.no_shows(flagged, 4)
        event = self.make_event(auto_approve=True)

        held = process_rsvp(event, flagged)
        clean = process_rsvp(event, self.make_user())

        held = EventSignup.objects.nocache().get(pk=held.pk)
        self.assertEqual(held.status, SignupStatus.PENDING_APPROVAL)
        self.assertEqual(held.unmet_requirements, [CODE])
        [reason] = held.eligibility_reasons
        self.assertEqual(reason["severity"], "needs_approval")
        self.assertEqual(reason["rule"], "org-conduct-threshold")
        self.assertEqual(clean.status, SignupStatus.APPROVED)

    def _open_waitlisted(self, user: CustomUser) -> EventSignup:
        other = self.make_event(max_players=0)
        return EventSignup.objects.create(
            event=other,
            user=user,
            status=SignupStatus.WAITLISTED,
            waitlist_position=1,
        )

    def test_refresh_after_finalize(self) -> None:
        self.enable(require_approval_enabled=True)
        member = self.make_user()
        self.no_shows(member, 2)
        open_signup = self._open_waitlisted(member)
        done = self.make_event(
            state=EventState.COMPLETED, scheduled_at=tz.now() - timedelta(hours=3)
        )
        self.signup(done, member, SignupStatus.APPROVED)
        self.outcome(
            member,
            event=done,
            outcome=Outcome.NO_SHOW,
            source="staff",
            finalized=False,
            set_by=self.admin,
            reason="did not show",
        )
        self.assertEqual(refresh_unmet_requirements(self.org_user(member)), 0)

        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                finalize_event_outcomes(done, now=tz.now(), actor=None)

        open_signup.refresh_from_db()
        self.assertEqual(open_signup.unmet_requirements, [CODE])

    def test_refresh_after_staff_edit(self) -> None:
        self.enable(require_approval_enabled=True)
        member = self.make_user()
        self.no_shows(member, 2)
        open_signup = self._open_waitlisted(member)
        done = self.make_event(
            state=EventState.COMPLETED,
            scheduled_at=tz.now() - timedelta(hours=3),
            conduct_finalized_at=tz.now(),
        )
        self.signup(done, member, SignupStatus.APPROVED)

        with self.captureOnCommitCallbacks(execute=True):
            set_outcomes(
                done,
                actor=self.admin,
                changes=[(self.org_user(member), Outcome.NO_SHOW)],
                reason="did not show",
            )

        open_signup.refresh_from_db()
        self.assertEqual(open_signup.unmet_requirements, [CODE])

    def held_open_signup(self) -> EventSignup:
        member = self.make_user()
        self.no_shows(member, 4)
        open_signup = self._open_waitlisted(member)
        refresh_unmet_requirements(self.org_user(member))
        open_signup.refresh_from_db()
        self.assertEqual(open_signup.unmet_requirements, [CODE])
        return open_signup

    def test_settings_toggle_off_clears_stored_code(self) -> None:
        self.enable(require_approval_enabled=True)
        open_signup = self.held_open_signup()

        with self.captureOnCommitCallbacks(execute=True):
            update_conduct_settings(
                self.org,
                actor=self.admin,
                changes={"require_approval_enabled": False},
            )

        open_signup.refresh_from_db()
        self.assertEqual(open_signup.unmet_requirements, [])

    def test_settings_toggle_on_badges_open_signups(self) -> None:
        self.enable()
        member = self.make_user()
        self.no_shows(member, 4)
        open_signup = self._open_waitlisted(member)
        closed = self.make_event(state=EventState.COMPLETED)
        closed_signup = EventSignup.objects.create(
            event=closed, user=member, status=SignupStatus.WAITLISTED
        )

        with self.captureOnCommitCallbacks(execute=True):
            update_conduct_settings(
                self.org, actor=self.admin, changes={"block_enabled": True}
            )

        open_signup.refresh_from_db()
        closed_signup.refresh_from_db()
        self.assertEqual(open_signup.unmet_requirements, [CODE])
        self.assertEqual(closed_signup.unmet_requirements, [])

    def test_leaderboard_toggle_skips_refresh(self) -> None:
        self.enable(require_approval_enabled=True)

        with (
            patch("org.conduct.services.refresh_org_unmet_requirements") as refresh,
            self.captureOnCommitCallbacks(execute=True),
        ):
            update_conduct_settings(
                self.org, actor=self.admin, changes={"leaderboard_public": True}
            )

        refresh.assert_not_called()

    def test_feature_lock_clears_stored_code(self) -> None:
        self.enable(block_enabled=True)
        open_signup = self.held_open_signup()
        site_admin = self.make_user()
        site_admin.is_staff = True
        site_admin.save()
        client = APIClient()
        client.force_authenticate(site_admin)

        with self.captureOnCommitCallbacks(execute=True):
            resp = client.put(
                reverse("org-features", args=[self.org.pk]),
                {"feature": "conduct", "enabled": False},
                format="json",
            )

        self.assertEqual(resp.status_code, 200, resp.content)
        open_signup.refresh_from_db()
        self.assertEqual(open_signup.unmet_requirements, [])

    def test_no_refresh_without_hold_modes(self) -> None:
        self.enable(back_of_line_enabled=True)
        member = self.make_user()
        self.no_shows(member, 2)
        done = self.make_event(
            state=EventState.COMPLETED,
            scheduled_at=tz.now() - timedelta(hours=3),
            conduct_finalized_at=tz.now(),
        )
        self.signup(done, member, SignupStatus.APPROVED)

        with (
            patch("org.conduct.services.refresh_unmet_requirements") as refresh,
            self.captureOnCommitCallbacks(execute=True),
        ):
            set_outcomes(
                done,
                actor=self.admin,
                changes=[(self.org_user(member), Outcome.NO_SHOW)],
                reason="did not show",
            )

        refresh.assert_not_called()


_GATE_PATCHES = (
    "events.admission.conduct_gate",
    "events.eligibility.checks.conduct.conduct_gate",
    "events.eligibility.store.conduct_gate",
    "events.services.conduct_gate",
)


def _gate_off(*_a: object, **_k: object) -> ConductGate:
    return GATE_OFF


@override_settings(CACHEOPS_ENABLED=False)
class QueryBudgetTest(ConductTestCase):
    def _run(
        self,
        action: Callable[[], object],
        snapshot: Callable[[], object],
        *,
        mode: Literal["baseline", "locked", "unlocked"],
    ) -> tuple[int, object]:
        with transaction.atomic():
            if mode == "unlocked":
                self.unlock()
            if mode == "baseline":
                patches = [patch(target, _gate_off) for target in _GATE_PATCHES]
                for p in patches:
                    p.start()
                try:
                    with CaptureQueriesContext(connection) as ctx:
                        action()
                finally:
                    for p in patches:
                        p.stop()
            else:
                with CaptureQueriesContext(connection) as ctx:
                    action()
            result = snapshot()
            transaction.set_rollback(True)
        return len(ctx.captured_queries), result

    def assert_budget(
        self,
        action: Callable[[], object],
        snapshot: Callable[[], object],
        *,
        gates_built: int,
    ) -> None:
        baseline, base_result = self._run(action, snapshot, mode="baseline")
        locked, locked_result = self._run(action, snapshot, mode="locked")
        unlocked, unlocked_result = self._run(action, snapshot, mode="unlocked")

        self.assertEqual(locked, baseline + gates_built)
        self.assertEqual(unlocked, baseline + 2 * gates_built)
        self.assertEqual(locked_result, base_result)
        self.assertEqual(unlocked_result, base_result)

    def _signups(self, event: Event) -> list[tuple[int, str, int | None, list[str]]]:
        return [
            (s.user_id, s.status, s.waitlist_position, s.unmet_requirements)
            for s in EventSignup.objects.nocache().filter(event=event).order_by("pk")
        ]

    def test_ensure_self_serve(self) -> None:
        event = self.make_event()
        user = self.make_user()

        self.assert_budget(
            lambda: ensure_self_serve(event, user), lambda: None, gates_built=1
        )

    def test_process_rsvp(self) -> None:
        event = self.make_event(max_players=10)
        user = self.make_user()

        self.assert_budget(
            lambda: process_rsvp(event, user),
            lambda: self._signups(event),
            gates_built=2,
        )

    def test_promote_from_waitlist(self) -> None:
        event = self.make_event(max_players=2)
        for position in (1, 2, 3):
            EventSignup.objects.create(
                event=event,
                user=self.make_user(),
                status=SignupStatus.WAITLISTED,
                waitlist_position=position,
            )

        self.assert_budget(
            lambda: _promote_from_waitlist(event),
            lambda: self._signups(event),
            gates_built=1,
        )

    def test_back_of_line_promotion_scores_once(self) -> None:
        self.unlock()
        OrgConductSettings.objects.create(
            organization=self.org,
            back_of_line_enabled=True,
            require_approval_enabled=True,
        )
        event = self.make_event(max_players=2)
        for position in (1, 2, 3):
            EventSignup.objects.create(
                event=event,
                user=self.make_user(),
                status=SignupStatus.WAITLISTED,
                waitlist_position=position,
            )

        with CaptureQueriesContext(connection) as ctx:
            promoted = _promote_from_waitlist(event)

        self.assertEqual(len(promoted), 2)
        score_queries = [
            q["sql"]
            for q in ctx.captured_queries
            if AttendanceOutcome._meta.db_table in q["sql"]
        ]
        self.assertEqual(len(score_queries), 1, score_queries)

    def test_refresh_unmet_requirements(self) -> None:
        user = self.make_user()
        events = [
            self.make_event(max_players=0, require_steam_id=True) for _ in range(2)
        ]
        for event in events:
            EventSignup.objects.create(
                event=event,
                user=user,
                status=SignupStatus.WAITLISTED,
                waitlist_position=1,
            )
        org_user = self.org_user(user)

        self.assert_budget(
            lambda: refresh_unmet_requirements(org_user),
            lambda: [self._signups(event) for event in events],
            gates_built=1,
        )


class BackOfLineTest(ConductTestCase):
    def setUp(self) -> None:
        self.unlock()

    def enable(self, **toggles: bool) -> OrgConductSettings:
        return OrgConductSettings.objects.create(organization=self.org, **toggles)

    def flagged_member(self) -> CustomUser:
        user = self.make_user()
        now = tz.now()
        for days in range(1, 5):
            self.outcome(
                user, outcome=Outcome.NO_SHOW, starts_at=now - timedelta(days=days)
            )
        return user

    def full_event_with_line(
        self, *, max_players: int = 1, **overrides: object
    ) -> tuple[Event, list[EventSignup], EventSignup, EventSignup]:
        event = self.make_event(max_players=max_players, **overrides)
        seated = [process_rsvp(event, self.make_user()) for _ in range(max_players)]
        flagged = process_rsvp(event, self.flagged_member())
        clean = process_rsvp(event, self.make_user())
        for signup in (flagged, clean):
            self.assertEqual(signup.status, SignupStatus.WAITLISTED)
        return event, seated, flagged, clean

    def reload(self, signup: EventSignup) -> EventSignup:
        return EventSignup.objects.nocache().get(pk=signup.pk)

    def test_flagged_promoted_after_unflagged(self) -> None:
        self.enable(back_of_line_enabled=True)
        _event, seated, flagged, clean = self.full_event_with_line()

        cancel_signup(seated[0])

        self.assertEqual(self.reload(clean).status, SignupStatus.APPROVED)
        self.assertEqual(self.reload(flagged).status, SignupStatus.WAITLISTED)

    def test_flagged_seated_when_seat_free(self) -> None:
        self.enable(back_of_line_enabled=True)
        event = self.make_event(max_players=2)

        signup = process_rsvp(event, self.flagged_member())

        self.assertEqual(signup.status, SignupStatus.APPROVED)
        self.assertIsNone(signup.waitlist_position)

    def test_public_line_rank_unchanged(self) -> None:
        self.enable(back_of_line_enabled=True)
        event, _seated, flagged, clean = self.full_event_with_line()
        client = APIClient()
        client.force_authenticate(self.make_user())

        resp = client.get(reverse("event-signup-list"), {"event": event.pk})

        self.assertEqual(resp.status_code, 200, resp.content)
        ranks = {row["id"]: row["line_rank"] for row in resp.json()}
        self.assertLess(ranks[flagged.pk], ranks[clean.pk])

    def test_disabled_uses_plain_order(self) -> None:
        _event, seated, flagged, clean = self.full_event_with_line()

        cancel_signup(seated[0])

        self.assertEqual(self.reload(flagged).status, SignupStatus.APPROVED)
        self.assertEqual(self.reload(clean).status, SignupStatus.WAITLISTED)

    def test_hold_tier_above_back_of_line_threshold_not_deferred(self) -> None:
        OrgConductSettings.objects.create(
            organization=self.org,
            back_of_line_enabled=True,
            back_of_line_below=Decimal("0.01"),
            require_approval_enabled=True,
            require_approval_below=Decimal("0.99"),
        )
        _event, seated, flagged, clean = self.full_event_with_line()

        cancel_signup(seated[0])

        flagged = self.reload(flagged)
        self.assertEqual(flagged.status, SignupStatus.PENDING_APPROVAL)
        self.assertEqual(flagged.unmet_requirements, [CODE])
        self.assertEqual(self.reload(clean).status, SignupStatus.WAITLISTED)

    def test_deferred_path_promotion_side_effects(self) -> None:
        self.enable(back_of_line_enabled=True, require_approval_enabled=True)
        tournament = Tournament.objects.create(
            name="Back Of Line Roster", date_played=tz.now(), state="future"
        )
        _event, seated, flagged, clean = self.full_event_with_line(
            max_players=2, tournament=tournament
        )

        cancel_signup(seated[0])
        clean = self.reload(clean)
        self.assertEqual(clean.status, SignupStatus.APPROVED)
        self.assertEqual(self.reload(flagged).status, SignupStatus.WAITLISTED)

        cancel_signup(seated[1])
        flagged = self.reload(flagged)

        self.assertEqual(flagged.status, SignupStatus.PENDING_APPROVAL)
        self.assertEqual(flagged.unmet_requirements, [CODE])
        self.assertIsNone(flagged.waitlist_position)
        self.assertEqual(clean.unmet_requirements, [])
        self.assertIsNone(clean.waitlist_position)
        roster = set(tournament.users.values_list("pk", flat=True))
        self.assertIn(clean.user_id, roster)
        self.assertNotIn(flagged.user_id, roster)
