import unittest
from datetime import UTC, datetime

# django-test-migrations is a dev dep; a stale CI image may lack it.
try:
    from django_test_migrations.contrib.unittest_case import MigratorTestCase
except ImportError as _import_error:  # pragma: no cover
    raise unittest.SkipTest(
        "django-test-migrations not installed — rebuild backend-dev image "
        "to pick up the new dev dep from pyproject.toml."
    ) from _import_error

CREATED = datetime(2026, 11, 1, 18, 0, tzinfo=UTC)
LATER = datetime(2026, 11, 1, 19, 0, tzinfo=UTC)


class BackfillChatMembershipMigrationTest(MigratorTestCase):
    """draft 0003: live drafts get tenure rows dated to draft creation."""

    migrate_from = ("draft", "0002_herodraftchat")
    migrate_to = ("draft", "0003_backfill_herodraft_chat_memberships")

    def prepare(self) -> None:
        apps = self.old_state.apps
        User = apps.get_model("app", "CustomUser")
        Tournament = apps.get_model("app", "Tournament")
        Team = apps.get_model("app", "Team")
        Game = apps.get_model("app", "Game")
        HeroDraft = apps.get_model("draft", "HeroDraft")
        DraftTeam = apps.get_model("draft", "DraftTeam")
        Membership = apps.get_model("draft", "HeroDraftChatMembership")

        names = ("cap_a", "mem_a", "cap_b", "mem_b", "both", "connected", "left")
        self.users = {n: User.objects.create(username=f"bf_{n}").pk for n in names}
        tournament = Tournament.objects.create(name="Backfill", date_played=CREATED)

        def draft(state: str) -> tuple[int, int, int]:
            a = Team.objects.create(
                name=f"A {state}", tournament=tournament, captain_id=self.users["cap_a"]
            )
            b = Team.objects.create(
                name=f"B {state}", tournament=tournament, captain_id=self.users["cap_b"]
            )
            a.members.add(
                self.users["mem_a"],
                self.users["both"],
                self.users["connected"],
                self.users["left"],
            )
            b.members.add(self.users["mem_b"], self.users["both"])
            game = Game.objects.create(
                tournament=tournament, radiant_team=a, dire_team=b
            )
            hd = HeroDraft.objects.create(game=game, state=state)
            HeroDraft.objects.filter(pk=hd.pk).update(created_at=CREATED)
            DraftTeam.objects.create(draft=hd, tournament_team=a)
            DraftTeam.objects.create(draft=hd, tournament_team=b)
            return hd.pk, a.pk, b.pk

        self.live, self.team_a, self.team_b = draft("drafting")
        self.waiting, _, _ = draft("waiting_for_captains")
        self.done, _, _ = draft("completed")
        self.abandoned, _, _ = draft("abandoned")

        Membership.objects.create(
            draft_id=self.live,
            team_id=self.team_a,
            user_id=self.users["connected"],
            joined_at=LATER,
        )
        Membership.objects.create(
            draft_id=self.live,
            team_id=self.team_a,
            user_id=self.users["left"],
            joined_at=CREATED,
            left_at=LATER,
        )

    def rows(self, draft_id: int) -> dict[str, tuple[int, datetime, datetime | None]]:
        Membership = self.new_state.apps.get_model("draft", "HeroDraftChatMembership")
        by_pk = {pk: name for name, pk in self.users.items()}
        return {
            by_pk[user_id]: (team_id, joined_at, left_at)
            for user_id, team_id, joined_at, left_at in Membership.objects.filter(
                draft_id=draft_id
            ).values_list("user_id", "team_id", "joined_at", "left_at")
        }

    def test_live_drafts_seeded_at_creation(self) -> None:
        self.assertEqual(
            self.rows(self.live),
            {
                "cap_a": (self.team_a, CREATED, None),
                "mem_a": (self.team_a, CREATED, None),
                "cap_b": (self.team_b, CREATED, None),
                "mem_b": (self.team_b, CREATED, None),
                "connected": (self.team_a, LATER, None),
                "left": (self.team_a, CREATED, LATER),
            },
        )
        self.assertEqual(
            set(self.rows(self.waiting)),
            {"cap_a", "mem_a", "cap_b", "mem_b", "connected", "left"},
        )

    def test_closed_drafts_untouched(self) -> None:
        self.assertEqual(self.rows(self.done), {})
        self.assertEqual(self.rows(self.abandoned), {})
