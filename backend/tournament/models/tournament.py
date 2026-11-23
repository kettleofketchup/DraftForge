from typing import TYPE_CHECKING

from django.conf import settings
from django.db import models
from django.db.models import QuerySet

from app.cache_utils import invalidate_obj
from app.models import CustomUser
from common.game import GameType
from lobby.passwords import generate_password
from tournament.choices import (
    TOURNAMENT_TYPE_CHOICES,
    DotaLobbyLaunch,
    DotaLobbyMode,
    DraftStyles,
    GameMode,
)

if TYPE_CHECKING:
    from draft.models import DraftOptions
    from tournament.models.team import Team

User = settings.AUTH_USER_MODEL


class Tournament(models.Model):
    STATE_CHOICES = [
        ("future", "Future"),
        ("in_progress", "In Progress"),
        ("past", "Past"),
    ]
    name = models.CharField(max_length=255)
    date_played = models.DateTimeField(
        help_text="Tournament date and time (stored in UTC)"
    )
    timezone = models.CharField(
        max_length=50,
        default="UTC",
        help_text="Tournament timezone (e.g., 'America/New_York', 'Europe/London')",
    )
    users = models.ManyToManyField(User, related_name="tournaments")
    # teams: reverse accessor of Team.tournament
    winning_team = models.OneToOneField(
        "tournament.Team",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tournaments_won",
    )

    state = models.CharField(max_length=20, choices=STATE_CHOICES, default="future")
    tournament_type = models.CharField(
        max_length=30, choices=TOURNAMENT_TYPE_CHOICES, default="double_elimination"
    )

    steam_league_id = models.IntegerField(
        null=True,
        blank=True,
        default=None,
        help_text="Steam league ID for match linking",
        db_column="league_id",  # Keep existing column name for backwards compatibility
    )
    league = models.ForeignKey(
        "league.League",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tournaments",
        db_column="league_fk_id",
    )

    game_type = models.IntegerField(
        choices=GameType.choices,
        default=GameType.DOTA2,
    )
    draft_type = models.CharField(
        max_length=10,
        choices=[(s.value, s.value.title()) for s in DraftStyles],
        default=DraftStyles.shuffle.value,
    )
    people_per_team = models.IntegerField(default=5)
    number_of_teams = models.IntegerField(null=True, blank=True)
    game_mode = models.CharField(
        max_length=20, choices=GameMode.choices, default=GameMode.NORMAL
    )
    custom_game_name = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Custom game/lobby name (for custom game mode)",
    )
    captains_draft_time = models.IntegerField(
        default=10,
        help_text="Seconds per draft pick in Captain's Mode",
    )
    lobby_steam_league_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="Steam league ID for Dota 2 lobby ticket",
    )
    auto_create_hero_drafts = models.BooleanField(default=False)
    discord_send_draft_link = models.BooleanField(default=True)
    discord_send_herodraft_link = models.BooleanField(default=True)
    # dota_lobby integration (lobby app). Off by default; the global
    # DOTA_LOBBY_ENABLED setting must also be on.
    dota_lobby_mode = models.CharField(
        max_length=8, choices=DotaLobbyMode.choices, default=DotaLobbyMode.OFF
    )
    dota_lobby_launch = models.CharField(
        max_length=8, choices=DotaLobbyLaunch.choices, default=DotaLobbyLaunch.MANUAL
    )
    dota_lobby_region = models.CharField(
        max_length=32,
        blank=True,
        default="",
        help_text="dota_lobby region name; empty uses DOTA_LOBBY_REGION",
    )
    discord_send_lobby_info = models.BooleanField(
        default=False,
        help_text="DM rostered players the lobby name and password",
    )
    # The password of every lobby created for this tournament: copied from
    # the source event, or generated for a standalone tournament once lobbies
    # are enabled (lobby.passwords). Never in public serializers.
    dota_lobby_password = models.CharField(max_length=32, blank=True, default="")

    def __str__(self) -> str:
        return self.name

    def save(self, *args: object, **kwargs: object) -> None:
        if self.dota_lobby_mode != DotaLobbyMode.OFF and not self.dota_lobby_password:
            self.dota_lobby_password = generate_password()
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = {*update_fields, "dota_lobby_password"}
        super().save(*args, **kwargs)
        # Self-invalidation handled by cacheops post_save signal; the
        # cascade to league + org refreshes those parents' embedded
        # tournament list. Targeted invalidate_obj() rather than
        # invalidate_model() so unrelated tournaments stay cached.
        if self.league:
            invalidate_obj(self.league)
            if self.league.organization:
                invalidate_obj(self.league.organization)

    class Meta:
        db_table = "app_tournament"
        indexes = [
            models.Index(fields=["name"]),
            models.Index(fields=["-date_played"]),
            models.Index(fields=["state"]),
            models.Index(fields=["league"]),
        ]

    @property
    def captains(self) -> "list[CustomUser] | QuerySet[CustomUser]":
        """
        Returns all users who are captains in this tournament.
        This is used to populate the draft choices.
        """
        if not self.users.exists():
            return []
        if not self.teams.exists():
            return []
        return self.users.filter(teams_as_captain__tournament=self).distinct()

    def draft_eligible_teams(self) -> "QuerySet[Team]":
        """Teams whose captain is in the tournament's player pool.

        Not cached: cacheops does not invalidate on subquery tables.
        """
        return self.teams.nocache().filter(captain_id__in=self.users.values("pk"))

    def draft_ineligible_teams(self) -> "QuerySet[Team]":
        return self.teams.nocache().exclude(
            pk__in=self.draft_eligible_teams().values("pk")
        )

    def draft_locked_user_ids(self) -> "QuerySet[CustomUser]":
        """Members of teams outside the draft; they are not draftable."""
        return (
            CustomUser.objects.nocache()
            .filter(teams_as_member__in=self.draft_ineligible_teams())
            .values("pk")
        )

    @property
    def linked_steam_league_id(self) -> int | None:
        """Steam league id resolved via the parent League FK.

        The legacy `Tournament.steam_league_id` field is ignored. Callers doing
        Steam match lookups should use this property so behavior follows
        the linked League and edits to League.steam_league_id take effect
        without per-tournament duplication.
        """
        if not self.league_id:
            return None
        return self.league.steam_league_id

    def get_draft_options(self, *, fresh: bool = False) -> "DraftOptions":
        options_model = self._meta.get_field("draft_options").related_model
        manager = options_model.objects.nocache() if fresh else options_model.objects
        options, _ = manager.get_or_create(tournament=self)
        return options
