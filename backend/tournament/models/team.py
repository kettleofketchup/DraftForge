from enum import StrEnum

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import QuerySet

from app.cache_utils import invalidate_after_commit
from app.models import CustomUser
from tournament.models.game import Game
from tournament.models.tournament import Tournament

User = settings.AUTH_USER_MODEL


class LeadershipProblem(StrEnum):
    CAPTAIN_NOT_MEMBER = "captain_not_member"
    DEPUTY_NOT_MEMBER = "deputy_not_member"
    DEPUTY_IS_CAPTAIN = "deputy_is_captain"

    @property
    def message(self) -> str:
        return _LEADERSHIP_MESSAGES[self]


_LEADERSHIP_MESSAGES: dict[LeadershipProblem, str] = {
    LeadershipProblem.CAPTAIN_NOT_MEMBER: "Captain must be a member of the team.",
    LeadershipProblem.DEPUTY_NOT_MEMBER: "Deputy captain must be a member of the team.",
    LeadershipProblem.DEPUTY_IS_CAPTAIN: "Deputy captain cannot be the same as captain.",
}


class Team(models.Model):
    tournament = models.ForeignKey(
        Tournament,
        related_name="teams",
        on_delete=models.CASCADE,
        null=True,  # Allow null for legacy data/migrations
        blank=True,
    )
    name = models.CharField(max_length=255)
    captain = models.ForeignKey(
        User,
        related_name="teams_as_captain",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
    )
    deputy_captain = models.ForeignKey(
        User,
        related_name="teams_as_deputy_captain",
        on_delete=models.SET_NULL,
        blank=True,
        null=True,
        help_text="Next in line for captain if captain is removed",
    )
    draft_order = models.PositiveSmallIntegerField(
        default=0,
        blank=True,
        null=True,
        help_text="Order in which a team picks their players in the draft",
    )
    members = models.ManyToManyField(User, related_name="teams_as_member", blank=True)
    dropin_members = models.ManyToManyField(
        User, related_name="teams_as_dropin", blank=True
    )
    left_members = models.ManyToManyField(
        User, related_name="teams_as_left", blank=True
    )

    # LeagueUser-based membership (org-scoped MMR system)
    league_users = models.ManyToManyField(
        "league.LeagueUser",
        related_name="teams",
        blank=True,
        help_text="Team members as LeagueUser (for org-scoped MMR)",
    )

    current_points = models.IntegerField(default=0, blank=True)
    placement = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Final tournament placement (1=winner, 2=runner-up, etc.)",
    )

    draft_reserve_ms = models.IntegerField(null=True, blank=True)
    draft_is_ready = models.BooleanField(default=False)
    draft_is_connected = models.BooleanField(default=False)
    draft_has_connected = models.BooleanField(default=False)

    class Meta:
        db_table = "app_team"
        indexes = [
            models.Index(fields=["tournament"]),
            models.Index(fields=["name"]),
            models.Index(fields=["captain"]),
            models.Index(fields=["deputy_captain"]),
        ]

    @staticmethod
    def leadership_errors(
        member_pks: set[int],
        captain_pk: int | None,
        deputy_pk: int | None,
        *,
        check_captain: bool = True,
        check_deputy: bool = True,
    ) -> dict[str, str]:
        problems = Team.leadership_problems(
            member_pks,
            captain_pk,
            deputy_pk,
            check_captain=check_captain,
            check_deputy=check_deputy,
        )
        return {field: problem.message for field, problem in problems.items()}

    @staticmethod
    def leadership_problems(
        member_pks: set[int],
        captain_pk: int | None,
        deputy_pk: int | None,
        *,
        check_captain: bool = True,
        check_deputy: bool = True,
    ) -> dict[str, "LeadershipProblem"]:
        problems: dict[str, LeadershipProblem] = {}
        if check_captain and captain_pk is not None and captain_pk not in member_pks:
            problems["captain"] = LeadershipProblem.CAPTAIN_NOT_MEMBER
        if check_deputy and deputy_pk is not None and deputy_pk not in member_pks:
            problems["deputy_captain"] = LeadershipProblem.DEPUTY_NOT_MEMBER
        elif deputy_pk is not None and deputy_pk == captain_pk:
            problems["deputy_captain"] = LeadershipProblem.DEPUTY_IS_CAPTAIN
        return problems

    def replace_member(self, old: CustomUser, new: CustomUser) -> None:
        was_member = self.members.filter(pk=old.pk).exists()
        if was_member:
            self.members.add(new)
        update_fields: list[str] = []
        if self.captain_id == old.pk:
            self.captain = new
            update_fields.append("captain")
        if self.deputy_captain_id == old.pk:
            self.deputy_captain = new
            update_fields.append("deputy_captain")
        if (
            self.deputy_captain_id is not None
            and self.deputy_captain_id == self.captain_id
        ):
            self.deputy_captain = None
            update_fields.append("deputy_captain")
        if update_fields:
            self.save(update_fields=sorted(set(update_fields)))
        if was_member:
            self.members.remove(old)
        invalidate_after_commit(self, old, new)

    def reduce_members_to_captain(self) -> list[CustomUser]:
        """Leave only the captain as a member; returns the removed members.

        Add before remove: removing first can empty a team whose captain is
        not a member, and the removal signal then deletes it with its games.
        """
        if self.captain_id is None:
            raise ValueError(f"Team {self.pk} has no captain to reset to.")
        self.members.add(self.captain_id)
        removed = list(self.members.exclude(pk=self.captain_id))
        if removed:
            self.members.remove(*removed)
        return removed

    def reset_to_captain(self) -> list[CustomUser]:
        """Reset the team in place for a fresh draft; returns the removed members."""
        removed = self.reduce_members_to_captain()
        self.dropin_members.clear()
        self.left_members.clear()
        league = self.tournament.league if self.tournament_id else None
        self.league_users.set(
            self.league_users.model.objects.filter(
                user_id=self.captain_id, league=league
            )
            if league
            else []
        )
        self.deputy_captain = None
        self.draft_reserve_ms = None
        self.draft_is_ready = False
        self.draft_is_connected = False
        self.draft_has_connected = False
        self.current_points = self._meta.get_field("current_points").get_default()
        self.placement = self._meta.get_field("placement").get_default()
        self.save(
            update_fields=[
                "deputy_captain",
                "draft_reserve_ms",
                "draft_is_ready",
                "draft_is_connected",
                "draft_has_connected",
                "current_points",
                "placement",
            ]
        )
        invalidate_after_commit(self, *removed, self.captain)
        return removed

    def clean(self) -> None:
        super().clean()

        # Skip ManyToMany validation if team has no pk yet (being created)
        if not self.pk:
            return

        errors = Team.leadership_errors(
            set(self.members.values_list("pk", flat=True)),
            self.captain_id,
            self.deputy_captain_id,
        )
        if errors:
            raise ValidationError(errors)

    def __str__(self) -> str:
        return self.name

    @property
    def games(self) -> "QuerySet[Game]":
        return Game.objects.filter(
            models.Q(radiant_team=self) | models.Q(dire_team=self)
        )
