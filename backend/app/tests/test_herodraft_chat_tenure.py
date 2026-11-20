from datetime import date, timedelta
from typing import Any
from unittest import mock

from django.db import transaction
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from app.functions.herodraft import new_herodraft_for_game
from app.functions.herodraft_chat import (
    ChatViewer,
    resolve_chat_viewer,
    visible_messages,
)
from app.models import (
    CustomUser,
    Game,
    HeroDraft,
    HeroDraftChatMembership,
    HeroDraftChatMessage,
    HeroDraftState,
    Team,
    Tournament,
)
from app.services.draft_reset import reset_draft_teams
from app.services.team_management import follow_captain
from tests.test_demo import _reset_demo_herodraft
from tests.test_herodraft import (
    _setup_draft_state,
    get_herodraft_by_key,
    reset_herodraft,
)

Channel = HeroDraftChatMessage.Channel
Kind = HeroDraftChatMessage.Kind
RESYNC = "app.functions.herodraft_chat.broadcast_chat_resync"


class TenureFixture(TestCase):
    def setUp(self) -> None:
        def user(name: str) -> CustomUser:
            return CustomUser.objects.create_user(username=name, password="x")

        self.cap_a = user("ct_cap_a")
        self.mem_a = user("ct_mem_a")
        self.mem_a2 = user("ct_mem_a2")
        self.cap_b = user("ct_cap_b")
        self.mem_b = user("ct_mem_b")
        self.mem_b2 = user("ct_mem_b2")
        self.newbie = user("ct_newbie")
        self.tournament = Tournament.objects.create(
            name="Chat Tenure Tournament", date_played=date.today()
        )
        self.team_a = Team.objects.create(
            name="CT A", tournament=self.tournament, captain=self.cap_a
        )
        self.team_b = Team.objects.create(
            name="CT B", tournament=self.tournament, captain=self.cap_b
        )
        self.team_a.members.add(self.mem_a, self.mem_a2)
        self.team_b.members.add(self.mem_b, self.mem_b2)
        self.game = Game.objects.create(
            tournament=self.tournament,
            radiant_team=self.team_a,
            dire_team=self.team_b,
        )
        self.draft: HeroDraft = new_herodraft_for_game(self.game)
        self.draft.refresh_from_db()
        resync = mock.patch(RESYNC)
        self.resync = resync.start()
        self.addCleanup(resync.stop)

    def open_row(self, user: CustomUser) -> HeroDraftChatMembership | None:
        return HeroDraftChatMembership.objects.filter(
            draft=self.draft, user=user, left_at__isnull=True
        ).first()

    def team_msg(
        self, team: Team, sender: CustomUser, body: str
    ) -> HeroDraftChatMessage:
        return HeroDraftChatMessage.objects.create(
            draft=self.draft,
            channel=Channel.TEAM,
            team=team,
            sender=sender,
            kind=Kind.TEXT,
            body=body,
        )

    def viewer(self, user: CustomUser) -> ChatViewer:
        return resolve_chat_viewer(self.draft.pk, user)

    def bodies(self, user: CustomUser) -> list[str]:
        return [m["body"] for m in visible_messages(self.draft.pk, self.viewer(user))]

    def backdate(self, msg: HeroDraftChatMessage, seconds: int = 60) -> None:
        HeroDraftChatMessage.objects.filter(pk=msg.pk).update(
            created_at=timezone.now() - timedelta(seconds=seconds)
        )

    def resync_calls(self) -> list[tuple[Any, ...]]:
        return [c.args for c in self.resync.call_args_list]


class SeedTest(TenureFixture):
    def test_seed_on_draft_create(self) -> None:
        for user, team in (
            (self.cap_a, self.team_a),
            (self.mem_a, self.team_a),
            (self.mem_a2, self.team_a),
            (self.cap_b, self.team_b),
            (self.mem_b, self.team_b),
            (self.mem_b2, self.team_b),
        ):
            row = self.open_row(user)
            self.assertIsNotNone(row, user.username)
            assert row is not None
            self.assertEqual(row.team_id, team.pk)
            self.assertEqual(row.joined_at, self.draft.created_at)
        self.assertIsNone(self.open_row(self.newbie))

    def test_seed_skips_user_on_both_teams(self) -> None:
        both = CustomUser.objects.create_user(username="ct_both", password="x")
        team_c = Team.objects.create(
            name="CT C", tournament=self.tournament, captain=self.cap_a
        )
        team_d = Team.objects.create(
            name="CT D", tournament=self.tournament, captain=self.cap_b
        )
        team_c.members.add(both)
        team_d.members.add(both)
        game = Game.objects.create(
            tournament=self.tournament, radiant_team=team_c, dire_team=team_d
        )
        draft = new_herodraft_for_game(game)
        self.assertFalse(
            HeroDraftChatMembership.objects.filter(draft=draft, user=both).exists()
        )


class RosterSignalTest(TenureFixture):
    def test_members_add_opens_row_now(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            self.team_a.members.add(self.newbie)
        row = self.open_row(self.newbie)
        assert row is not None
        self.assertEqual(row.team_id, self.team_a.pk)
        self.assertGreater(row.joined_at, self.draft.created_at)
        self.assertIn(
            (self.draft.pk, [self.team_a.pk], [self.newbie.pk]), self.resync_calls()
        )

    def test_members_add_reverse_opens_row_now(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            self.newbie.teams_as_member.add(self.team_b)
        row = self.open_row(self.newbie)
        assert row is not None
        self.assertEqual(row.team_id, self.team_b.pk)
        self.assertGreater(row.joined_at, self.draft.created_at)
        self.assertIn(
            (self.draft.pk, [self.team_b.pk], [self.newbie.pk]), self.resync_calls()
        )

    def test_add_existing_member_keeps_joined_at(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            self.team_a.members.add(self.cap_a)
        row = self.open_row(self.cap_a)
        assert row is not None
        self.assertEqual(row.joined_at, self.draft.created_at)

    def test_transfer_b_to_a(self) -> None:
        before_a = self.team_msg(self.team_a, self.cap_a, "a-before")
        self.backdate(before_a)
        b_msg = self.team_msg(self.team_b, self.cap_b, "b-strat")
        self.backdate(b_msg)
        with self.captureOnCommitCallbacks(execute=True):
            self.team_b.members.remove(self.mem_b)
        with self.captureOnCommitCallbacks(execute=True):
            self.team_a.members.add(self.mem_b)
        rows = HeroDraftChatMembership.objects.filter(draft=self.draft, user=self.mem_b)
        b_row = rows.get(team=self.team_b)
        self.assertIsNotNone(b_row.left_at)
        a_row = rows.get(team=self.team_a)
        self.assertIsNone(a_row.left_at)
        self.assertGreater(a_row.joined_at, b_msg.created_at)
        after_a = self.team_msg(self.team_a, self.cap_a, "a-after")
        self.assertEqual(self.bodies(self.mem_b), [after_a.body])

    def test_members_remove_closes_row(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            self.team_a.members.remove(self.mem_a)
        self.assertIsNone(self.open_row(self.mem_a))
        self.assertIn(
            (self.draft.pk, [self.team_a.pk], [self.mem_a.pk]), self.resync_calls()
        )

    def test_members_remove_reverse_closes_row(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            self.mem_b.teams_as_member.remove(self.team_b)
        self.assertIsNone(self.open_row(self.mem_b))
        self.assertIn(
            (self.draft.pk, [self.team_b.pk], [self.mem_b.pk]), self.resync_calls()
        )

    def test_members_clear_closes_rows(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            self.team_b.members.clear()
        self.assertIsNone(self.open_row(self.mem_b))
        self.assertIsNone(self.open_row(self.mem_b2))
        captain_row = self.open_row(self.cap_b)
        self.assertIsNotNone(captain_row)
        calls = [
            c
            for c in self.resync_calls()
            if c[0] == self.draft.pk and c[1] == [self.team_b.pk]
        ]
        self.assertTrue(calls)
        self.assertEqual(sorted(calls[0][2]), sorted([self.mem_b.pk, self.mem_b2.pk]))

    def test_members_clear_reverse_closes_rows(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            self.mem_a.teams_as_member.clear()
        self.assertIsNone(self.open_row(self.mem_a))
        self.assertIn(
            (self.draft.pk, [self.team_a.pk], [self.mem_a.pk]), self.resync_calls()
        )

    def test_remove_captain_succession_closes_old_captain(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            self.team_a.members.add(self.cap_a)
        with self.captureOnCommitCallbacks(execute=True):
            self.team_a.members.remove(self.cap_a)
        self.team_a.refresh_from_db()
        successor = self.team_a.captain
        assert successor is not None
        self.assertIn(successor.pk, (self.mem_a.pk, self.mem_a2.pk))
        self.assertIsNone(self.open_row(self.cap_a))
        row = self.open_row(successor)
        assert row is not None
        self.assertEqual(row.joined_at, self.draft.created_at)

    def test_terminal_drafts_ignored(self) -> None:
        for state in (HeroDraftState.COMPLETED, HeroDraftState.ABANDONED):
            with self.subTest(state=state):
                HeroDraft.objects.filter(pk=self.draft.pk).update(state=state)
                self.resync.reset_mock()
                before = list(
                    HeroDraftChatMembership.objects.order_by("pk").values_list(
                        "pk", "left_at"
                    )
                )
                with self.captureOnCommitCallbacks(execute=True):
                    self.team_a.members.add(self.newbie)
                    self.team_b.members.remove(self.mem_b2)
                after = list(
                    HeroDraftChatMembership.objects.order_by("pk").values_list(
                        "pk", "left_at"
                    )
                )
                self.assertEqual(before, after)
                self.resync.assert_not_called()
                self.team_a.members.remove(self.newbie)
                self.team_b.members.add(self.mem_b2)

    def test_no_write_before_commit(self) -> None:
        with self.captureOnCommitCallbacks(execute=False) as callbacks:
            self.team_a.members.add(self.newbie)
            self.assertIsNone(self.open_row(self.newbie))
        self.assertTrue(callbacks)
        self.resync.assert_not_called()


class RepointTest(TenureFixture):
    def test_repoint_reseeds(self) -> None:
        cap_c = CustomUser.objects.create_user(username="ct_cap_c", password="x")
        mem_c = CustomUser.objects.create_user(username="ct_mem_c", password="x")
        team_c = Team.objects.create(
            name="CT C", tournament=self.tournament, captain=cap_c
        )
        team_c.members.add(mem_c)
        old_msg = self.team_msg(self.team_a, self.cap_a, "a-old")
        self.resync.reset_mock()
        before = timezone.now()
        with self.captureOnCommitCallbacks(execute=True):
            self.game.radiant_team = team_c
            self.game.save()
        for user in (self.cap_a, self.mem_a, self.mem_a2):
            self.assertIsNone(self.open_row(user), user.username)
        for user in (cap_c, mem_c):
            row = self.open_row(user)
            assert row is not None
            self.assertEqual(row.team_id, team_c.pk)
            self.assertGreaterEqual(row.joined_at, before)
        b_row = self.open_row(self.mem_b)
        assert b_row is not None
        self.assertEqual(b_row.joined_at, self.draft.created_at)
        self.resync.assert_not_called()
        self.assertNotIn(old_msg.body, self.bodies(cap_c))

    def test_side_swap_keeps_rows(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            self.game.radiant_team = self.team_b
            self.game.dire_team = self.team_a
            self.game.save()
        for user in (self.cap_a, self.mem_a, self.cap_b, self.mem_b):
            row = self.open_row(user)
            assert row is not None
            self.assertEqual(row.joined_at, self.draft.created_at)
        self.resync.assert_not_called()


class CaptainChangeTest(TenureFixture):
    def swap_captain(self, new: CustomUser) -> None:
        old = self.team_a.captain
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                self.team_a.captain = new
                self.team_a.save(update_fields=["captain"])
                follow_captain(self.team_a, old, new, actor=None)

    def test_captain_change_closes_and_opens_tenure(self) -> None:
        before = timezone.now()
        self.swap_captain(self.newbie)
        old_rows = HeroDraftChatMembership.objects.filter(
            draft=self.draft, user=self.cap_a
        )
        self.assertEqual(old_rows.count(), 1)
        closed = old_rows.get()
        assert closed.left_at is not None
        self.assertGreaterEqual(closed.left_at, before)
        row = self.open_row(self.newbie)
        assert row is not None
        self.assertEqual(row.team_id, self.team_a.pk)
        self.assertGreaterEqual(row.joined_at, before)
        self.assertIn(
            (self.draft.pk, [self.team_a.pk], [self.cap_a.pk, self.newbie.pk]),
            self.resync_calls(),
        )

    def test_old_captain_readded_sees_no_gap(self) -> None:
        self.swap_captain(self.newbie)
        gap = self.team_msg(self.team_a, self.newbie, "gap")
        self.backdate(gap, seconds=1)
        with self.captureOnCommitCallbacks(execute=True):
            self.team_a.members.add(self.cap_a)
        rows = HeroDraftChatMembership.objects.filter(
            draft=self.draft, user=self.cap_a
        ).order_by("pk")
        self.assertEqual(rows.count(), 2)
        self.assertIsNotNone(rows[0].left_at)
        self.assertIsNone(rows[1].left_at)
        self.assertNotIn("gap", self.bodies(self.cap_a))

    def test_new_captain_sees_only_post_swap(self) -> None:
        pre = self.team_msg(self.team_a, self.cap_a, "pre-swap")
        self.backdate(pre)
        self.swap_captain(self.newbie)
        post = self.team_msg(self.team_a, self.mem_a, "post-swap")
        self.assertEqual(self.bodies(self.newbie), [post.body])

    def test_captain_still_member_keeps_row(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            self.team_a.members.add(self.cap_a)
        self.swap_captain(self.mem_a)
        row = self.open_row(self.cap_a)
        assert row is not None
        self.assertEqual(row.joined_at, self.draft.created_at)
        mem_row = self.open_row(self.mem_a)
        assert mem_row is not None
        self.assertEqual(mem_row.joined_at, self.draft.created_at)

    def test_terminal_draft_no_captain_tenure(self) -> None:
        HeroDraft.objects.filter(pk=self.draft.pk).update(
            state=HeroDraftState.COMPLETED
        )
        self.resync.reset_mock()
        self.swap_captain(self.newbie)
        self.assertIsNotNone(self.open_row(self.cap_a))
        self.assertIsNone(self.open_row(self.newbie))
        self.resync.assert_not_called()


class ResetCleanupTest(TenureFixture):
    def setUp(self) -> None:
        super().setUp()
        self.team_a.members.add(self.cap_a)
        self.team_b.members.add(self.cap_b)
        self.tournament.users.add(
            self.cap_a, self.mem_a, self.mem_a2, self.cap_b, self.mem_b, self.mem_b2
        )
        self.team_msg(self.team_a, self.cap_a, "a-secret")
        self.team_msg(self.team_b, self.cap_b, "b-secret")
        HeroDraftChatMessage.objects.create(
            draft=self.draft,
            channel=Channel.ALL,
            team=None,
            sender=self.cap_a,
            kind=Kind.TEXT,
            body="gg",
        )

    def team_rows(self) -> tuple[int, int]:
        teams = [self.team_a.pk, self.team_b.pk]
        return (
            HeroDraftChatMessage.objects.filter(team_id__in=teams).count(),
            HeroDraftChatMembership.objects.filter(team_id__in=teams).count(),
        )

    def test_reset_draft_teams_force_deletes_chat(self) -> None:
        with self.captureOnCommitCallbacks(execute=True):
            with transaction.atomic():
                report = reset_draft_teams(self.tournament, force=True)
        self.assertEqual(
            sorted(t.pk for t in report.reset_teams),
            sorted([self.team_a.pk, self.team_b.pk]),
        )
        self.assertEqual(self.team_rows(), (0, 0))
        self.assertEqual(
            list(
                HeroDraftChatMessage.objects.filter(draft=self.draft).values_list(
                    "body", flat=True
                )
            ),
            ["gg"],
        )
        with self.captureOnCommitCallbacks(execute=True):
            self.team_a.members.add(self.newbie)
        self.assertEqual(self.bodies(self.newbie), ["gg"])

    def test_reset_chat_delete_rolls_back(self) -> None:
        before = self.team_rows()
        self.assertEqual(before[0], 2)
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                reset_draft_teams(self.tournament, force=True)
                self.assertEqual(self.team_rows(), (0, 0))
                raise RuntimeError("abort")
        self.assertEqual(self.team_rows(), before)


class TestResetEndpointsTest(TenureFixture):
    def setUp(self) -> None:
        super().setUp()
        self.team_msg(self.team_a, self.cap_a, "a-secret")
        HeroDraftChatMessage.objects.create(
            draft=self.draft,
            channel=Channel.ALL,
            team=None,
            sender=self.cap_a,
            kind=Kind.TEXT,
            body="gg",
        )
        HeroDraftChatMembership.objects.filter(
            draft=self.draft, user=self.mem_a
        ).update(left_at=timezone.now())

    def assert_reset_and_reseeded(self) -> None:
        self.assertEqual(
            HeroDraftChatMessage.objects.filter(draft=self.draft).count(), 0
        )
        rows = HeroDraftChatMembership.objects.filter(draft=self.draft)
        self.assertFalse(rows.filter(left_at__isnull=False).exists())
        self.draft.refresh_from_db()
        self.assertEqual(
            sorted(rows.values_list("user_id", flat=True)),
            sorted(
                u.pk
                for u in (
                    self.cap_a,
                    self.mem_a,
                    self.mem_a2,
                    self.cap_b,
                    self.mem_b,
                    self.mem_b2,
                )
            ),
        )
        self.assertTrue(
            all(r.joined_at == self.draft.created_at for r in rows),
        )

    def test_test_reset_endpoints_delete_chat(self) -> None:
        request = APIRequestFactory().post(
            f"/api/tests/herodraft/{self.draft.pk}/reset/"
        )
        response = reset_herodraft(request, draft_pk=self.draft.pk)
        self.assertEqual(response.status_code, 200)
        self.assert_reset_and_reseeded()

    def test_setup_draft_state_deletes_chat(self) -> None:
        _setup_draft_state(self.draft, "waiting_for_captains")
        self.assert_reset_and_reseeded()

    def test_demo_reset_deletes_chat(self) -> None:
        response = _reset_demo_herodraft(self.tournament)
        self.assertEqual(response.status_code, 200)
        self.assert_reset_and_reseeded()


class HeroDraftByKeyTest(TenureFixture):
    def setUp(self) -> None:
        super().setUp()
        self.tournament.name = "Real Tournament 38"
        self.tournament.save()
        self.game.round = 2
        self.game.bracket_type = "winners"
        self.game.position = 0
        self.game.save()
        env = mock.patch("tests.test_herodraft.isTestEnvironment", return_value=True)
        env.start()
        self.addCleanup(env.stop)

    def test_drafting_phase_returns_member_pks_and_active_round(self) -> None:
        HeroDraft.objects.filter(pk=self.draft.pk).update(
            is_manual_pause=True, paused_at=timezone.now()
        )
        request = APIRequestFactory().get("/api/tests/herodraft-by-key/drafting_phase/")
        response = get_herodraft_by_key(request, key="drafting_phase")
        self.assertEqual(response.status_code, 200)
        by_team = {
            dt["team_name"]: dt["member_pks"] for dt in response.data["draft_teams"]
        }
        self.assertEqual(
            by_team,
            {
                "CT A": sorted([self.mem_a.pk, self.mem_a2.pk]),
                "CT B": sorted([self.mem_b.pk, self.mem_b2.pk]),
            },
        )
        self.draft.refresh_from_db()
        self.assertEqual(self.draft.state, HeroDraftState.DRAFTING)
        self.assertFalse(self.draft.is_manual_pause)
        self.assertIsNone(self.draft.paused_at)
        active = list(self.draft.rounds.filter(state="active"))
        self.assertEqual([r.round_number for r in active], [1])
        self.assertIsNotNone(active[0].started_at)
        self.assertFalse(self.draft.draft_teams.filter(is_connected=True).exists())
        first_pick = self.draft.draft_teams.get(is_first_pick=True)
        self.assertEqual(active[0].draft_team_id, first_pick.pk)
