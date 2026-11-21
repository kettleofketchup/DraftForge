import random
from collections.abc import Callable, Iterable

from django.conf import settings
from django.db import models
from django.db.models import QuerySet
from django.db.utils import IntegrityError

from app.cache_utils import invalidate_after_commit, invalidate_obj
from app.models import CustomUser, Team, Tournament
from org.mmr import game_for_tournament, org_mmr_map
from telemetry.logging import get_logger

User = settings.AUTH_USER_MODEL

log = get_logger(__name__)


class TeamDraftState(models.TextChoices):
    PENDING = "pending", "Pending"
    DRAFTING = "drafting", "Drafting"
    PAUSED = "paused", "Paused"
    RESUMING = "resuming", "Resuming"
    COMPLETED = "completed", "Completed"


class TimeoutAction(models.TextChoices):
    SKIP_TURN = "skip_turn", "Skip turn"


class Draft(models.Model):
    tournament = models.OneToOneField(
        "app.Tournament",
        related_name="draft",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )
    DRAFT_STYLE_CHOICES = [
        ("snake", "Snake"),
        ("normal", "Normal"),
        ("shuffle", "Shuffle"),
    ]

    draft_style = models.CharField(
        max_length=10,
        choices=DRAFT_STYLE_CHOICES,
        default="snake",
        help_text="Draft style: snake, normal, or shuffle",
    )
    state = models.CharField(
        max_length=16,
        choices=TeamDraftState.choices,
        default=TeamDraftState.PENDING,
    )
    paused_at = models.DateTimeField(null=True, blank=True)
    resuming_until = models.DateTimeField(null=True, blank=True)
    is_manual_pause = models.BooleanField(default=False)

    class Meta:
        db_table = "app_draft"

    def __str__(self) -> str:
        return f"Draft {self.pk} in {self.tournament.name}"

    @property
    def active_round(self) -> "DraftRound | None":
        rounds = self._prefetched_rounds()
        if rounds is not None:
            return next((r for r in rounds if r.choice_id is None), None)
        return (
            self.draft_rounds.filter(choice__isnull=True)
            .order_by("pick_number")
            .first()
        )

    def _prefetched_rounds(self) -> "list[DraftRound] | None":
        """Prefetched rounds sorted by pick_number, or None when not prefetched."""
        rounds = getattr(self, "_prefetched_objects_cache", {}).get("draft_rounds")
        if rounds is None:
            return None
        return sorted(rounds, key=lambda r: r.pick_number)

    def lock_active_round(self) -> "DraftRound | None":
        return (
            self.draft_rounds.select_for_update()
            .filter(choice__isnull=True)
            .order_by("pick_number")
            .first()
        )

    @property
    def clock_armed(self) -> bool:
        return self.is_clock_armed(self.tournament.get_draft_options)

    def is_clock_armed(self, get_options: Callable[[], "DraftOptions"]) -> bool:
        if self.state not in (TeamDraftState.DRAFTING, TeamDraftState.RESUMING):
            return False
        if not get_options().timer_enabled:
            return False
        active = self.active_round
        return active is not None and active.started_at is not None

    def reset_timer_state(
        self, options: "DraftOptions", teams: "Iterable[Team] | None" = None
    ) -> None:
        self.state = (
            TeamDraftState.PENDING if options.timer_enabled else TeamDraftState.DRAFTING
        )
        self.paused_at = None
        self.resuming_until = None
        self.is_manual_pause = False
        for team in self.teams if teams is None else teams:
            team.draft_reserve_ms = options.reserve_time_ms
            team.draft_is_ready = False
            team.draft_is_connected = False
            team.draft_has_connected = False
            team.save(
                update_fields=[
                    "draft_reserve_ms",
                    "draft_is_ready",
                    "draft_is_connected",
                    "draft_has_connected",
                ]
            )
        self.save()

    def derive_legacy_state(self) -> str:
        rounds = self.draft_rounds.nocache()
        if not rounds.exists():
            return TeamDraftState.PENDING
        if not rounds.filter(choice__isnull=True).exists():
            return TeamDraftState.COMPLETED
        return TeamDraftState.DRAFTING

    def _emit_lobby_opened(self, options: "DraftOptions") -> None:
        # Cycle: draft.services.team_broadcast imports draft.models.
        from draft.services.team_broadcast import broadcast_event_after_commit

        event = DraftEvent.objects.create(
            draft=self,
            event_type="draft_lobby_opened",
            payload={
                "timer_enabled": True,
                "grace_time_ms": options.grace_time_ms,
                "reserve_time_ms": options.reserve_time_ms,
            },
        )
        broadcast_event_after_commit(event)

    def _emit_draft_started(self, team_count: int) -> None:
        # Cycle: draft.services.team_broadcast imports draft.models.
        from draft.services.team_broadcast import broadcast_event_after_commit

        event = DraftEvent.objects.create(
            draft=self,
            event_type="draft_started",
            payload={
                "draft_id": self.pk,
                "draft_style": self.draft_style,
                "team_count": team_count,
            },
        )
        broadcast_event_after_commit(event)

    def save(self, *args: object, **kwargs: object) -> None:
        super().save(*args, **kwargs)
        # Invalidate tournament cache when draft is modified
        invalidate_obj(self.tournament)

    def _simulate_draft(
        self, draft_style: str = "snake"
    ) -> dict[int, list[tuple[int, int]]]:
        """
        Simulate a draft where each captain picks the highest MMR player available.
        Returns a dict with team_id -> list of picked players (including captain).

        Args:
            draft_style: "snake" or "normal"
        """

        def get_simulation_data(
            draft_style: str = draft_style,
        ) -> dict[int, list[tuple[int, int]]]:
            teams = list(self.teams.order_by("draft_order"))
            log.debug(
                "simulation_teams_loaded",
                system="tournament",
                subsystem="draft",
                draft_style=draft_style,
                team_count=len(teams),
            )
            if not teams:
                return {}

            # Get organization for MMR lookups
            org = None
            if self.tournament.league:
                org = self.tournament.league.organization

            mmr_map: dict[int, int] = {}
            if org:
                mmr_map = org_mmr_map(
                    org.pk,
                    self.tournament.users.values_list("id", flat=True),
                    game_for_tournament(self.tournament),
                )

            # Get all available players (excluding captains) sorted by MMR desc
            all_player_ids = list(
                self.tournament.users.nocache()
                .exclude(teams_as_captain__tournament=self.tournament)
                .exclude(pk__in=self.tournament.draft_locked_user_ids())
                .values_list("id", flat=True)
            )
            available_players = sorted(
                [(pid, mmr_map.get(pid, 0)) for pid in all_player_ids],
                key=lambda x: x[1],
                reverse=True,
            )

            # Initialize team rosters with captains
            team_rosters = {}
            for team in teams:
                captain_mmr = mmr_map.get(team.captain_id, 0)
                team_rosters[team.id] = [(team.captain.id, captain_mmr)]

            # Simulate draft rounds (4 picks per team after captain)
            picks_per_team = 4
            num_teams = len(teams)
            total_picks = num_teams * picks_per_team
            pick_number = 1

            for round_num in range(picks_per_team):
                if draft_style == "snake":
                    # Snake draft: alternate direction each round
                    if round_num % 2 == 0:
                        # Forward: 1st, 2nd, 3rd, 4th team
                        pick_order = teams
                    else:
                        # Reverse: 4th, 3rd, 2nd, 1st team
                        pick_order = list(reversed(teams))
                else:  # normal
                    # Normal: always same order
                    pick_order = teams

                # Each team in the pick order gets one pick this round
                for team in pick_order:
                    if pick_number <= total_picks and available_players:
                        # Pick highest MMR available player
                        player_id, player_mmr = available_players.pop(0)
                        if player_mmr is None:
                            player_mmr = 0
                        team_rosters[team.id].append((player_id, player_mmr))

                        log.debug(
                            "simulation_pick",
                            system="tournament",
                            subsystem="draft",
                            draft_style=draft_style,
                            team_name=team.name,
                            player_id=player_id,
                            player_mmr=player_mmr,
                        )
                        pick_number += 1

            return team_rosters

        data = get_simulation_data(draft_style=draft_style)
        log.debug(
            "simulation_complete",
            system="tournament",
            subsystem="draft",
            draft_style=draft_style,
            team_count=len(data),
        )
        return data

    @property
    def snake_first_pick_mmr(self) -> int:
        """Calculate total MMR for first pick team in snake draft simulation."""
        simulation = self._simulate_draft("snake")
        if not simulation:
            return 0

        # First team in draft order
        first_team = self.teams.order_by("draft_order").first()
        if not first_team or first_team.id not in simulation:
            return 0
        return sum(mmr for _, mmr in simulation[first_team.id])

    @property
    def snake_last_pick_mmr(self) -> int:
        """Calculate total MMR for last pick team in snake draft simulation."""
        simulation = self._simulate_draft("snake")
        if not simulation:
            return 0

        # Last team in draft order
        last_team = self.teams.order_by("draft_order").last()
        if not last_team or last_team.id not in simulation:
            return 0

        return sum(mmr for _, mmr in simulation[last_team.id])

    @property
    def normal_first_pick_mmr(self) -> int:
        """Calculate total MMR for first pick team in normal draft simulation."""
        simulation = self._simulate_draft("normal")
        if not simulation:
            return 0

        # First team in draft order
        first_team = self.teams.order_by("draft_order").first()
        if not first_team or first_team.id not in simulation:
            return 0

        return sum(mmr for _, mmr in simulation[first_team.id])

    @property
    def normal_last_pick_mmr(self) -> int:
        """Calculate total MMR for last pick team in normal draft simulation."""
        simulation = self._simulate_draft("normal")
        if not simulation:
            return 0

        # Last team in draft order
        last_team = self.teams.order_by("draft_order").last()
        if not last_team or last_team.id not in simulation:
            return 0

        return sum(mmr for _, mmr in simulation[last_team.id])

    @property
    def current_draft_first_pick_mmr(self) -> int:
        """Calculate total MMR for first pick team using current draft style."""
        simulation = self._simulate_draft(self.draft_style)
        if not simulation:
            return 0

        first_team = self.teams.order_by("draft_order").first()
        if not first_team or first_team.id not in simulation:
            return 0

        return sum(mmr for _, mmr in simulation[first_team.id])

    @property
    def current_draft_last_pick_mmr(self) -> int:
        """Calculate total MMR for last pick team using current draft style."""
        simulation = self._simulate_draft(self.draft_style)
        if not simulation:
            return 0

        last_team = self.teams.order_by("draft_order").last()
        if not last_team or last_team.id not in simulation:
            return 0

        return sum(mmr for _, mmr in simulation[last_team.id])

    @property
    def teams(self) -> QuerySet[Team]:
        """The teams taking part in this draft."""
        return self.tournament.draft_eligible_teams()

    @property
    def users(self) -> list[CustomUser] | QuerySet[CustomUser]:
        if not self.tournament.users.exists():
            return []

        return self.tournament.users.all()

    @property
    def users_remaining(self) -> list[CustomUser] | QuerySet[CustomUser]:
        """
        Returns users that are not already in teams.
        This is used to populate the draft choices.
        """
        if not self.tournament.users.exists():
            return []
        picked_user_ids = list(
            self.draft_rounds.filter(choice__isnull=False).values_list(
                "choice_id", flat=True
            )
        )
        log.debug(
            "draft_picked_user_ids",
            system="tournament",
            subsystem="draft",
            picked_user_ids=list(picked_user_ids),
        )
        captain_ids = list(
            self.tournament.teams.filter(captain__isnull=False).values_list(
                "captain_id", flat=True
            )
        )
        log.debug(
            "draft_captain_ids",
            system="tournament",
            subsystem="draft",
            captain_ids=captain_ids,
        )
        excluded_ids = set(picked_user_ids + captain_ids)
        log.debug(
            "draft_excluded_ids",
            system="tournament",
            subsystem="draft",
            excluded_count=len(excluded_ids),
        )
        return (
            self.tournament.users.nocache()
            .exclude(id__in=excluded_ids)
            .exclude(id__in=self.tournament.draft_locked_user_ids())
            .exclude(teams_as_member__tournament=self.tournament)
            .exclude(teams_as_dropin__tournament=self.tournament)
            .exclude(teams_as_left__tournament=self.tournament)
            .distinct()
        )

    @property
    def captains(self) -> QuerySet[CustomUser]:
        if not self.tournament.captains.exists():
            raise ValueError("Draft must be associated with a tournament.")

        return self.tournament.captains.all()

    @property
    def latest_round(self) -> int | None:
        """
        Returns the latest draft round.
        """
        rounds = self._prefetched_rounds()
        if rounds:
            latest = next((r for r in rounds if r.choice_id is None), rounds[-1])
            return latest.pk
        if not self.draft_rounds.exists():
            log.error(
                "no_draft_rounds_exist",
                system="tournament",
                subsystem="draft",
                draft_id=self.pk,
            )
            return

        latest_round = (
            self.draft_rounds.order_by("pick_number")
            .exclude(choice__isnull=False)
            .first()
        )
        if not latest_round:
            latest_round = self.draft_rounds.order_by("pick_number").last()

        return latest_round.pk

    def rebuild_teams(self, clear_only: bool = False) -> None:
        """
        Build teams based on the draft choices.

        Args:
            clear_only: If True, only clear teams to captain-only (for draft restart).
                       If False (default), also re-add players from existing draft rounds.
        """
        log.debug(
            "rebuild_teams_started",
            system="tournament",
            subsystem="draft",
            tournament_name=self.tournament.name if self.tournament else None,
        )
        if not self.tournament:
            raise ValueError("Draft must be associated with a tournament.")

        if not self.tournament.captains:
            raise ValueError("Draft must have captains to build teams.")
        log.debug(
            "rebuild_teams_clearing",
            system="tournament",
            subsystem="draft",
            tournament_name=self.tournament.name,
        )
        for team in self.teams:
            log.debug(
                "rebuild_team",
                system="tournament",
                subsystem="draft",
                team_name=team.name,
                tournament_name=self.tournament.name,
            )
            if clear_only:
                team.reset_to_captain()
            else:
                team.reduce_members_to_captain()
                invalidate_after_commit(team)

        # Skip re-adding draft choices if we're just clearing for a restart
        if clear_only:
            log.debug(
                "rebuild_teams_clear_only",
                system="tournament",
                subsystem="draft",
                draft_id=self.pk,
            )
            return

        for captain in self.captains.all():
            team = Team.objects.get(
                captain=captain,
                tournament=self.tournament,
            )

            for draft_round in self.draft_rounds.all():
                if not draft_round.captain == captain:
                    continue
                if not draft_round.choice:
                    continue  # Skip rounds with no choice (e.g., after restart)
                if (
                    team.left_members.nocache()
                    .filter(pk=draft_round.choice_id)
                    .exists()
                ):
                    continue
                log.debug(
                    "rebuild_teams_adding_pick",
                    system="tournament",
                    subsystem="draft",
                    team_name=team.name,
                    tournament_name=self.tournament.name,
                )
                team.members.add(draft_round.choice)
                team.save()

    def build_rounds(self, teams: "QuerySet[Team] | None" = None) -> None:
        """Rebuild the draft rounds for ``teams`` (default: ``Draft.teams``)."""
        if teams is None:
            teams = self.teams
        teams = teams.order_by("draft_order")
        log.debug(
            "build_rounds_started",
            system="tournament",
            subsystem="draft",
            draft_style=self.draft_style,
            draft_id=self.pk,
        )

        # Clear existing draft rounds
        for round in self.draft_rounds.all():
            log.debug(
                "build_rounds_clearing_existing",
                system="tournament",
                subsystem="draft",
                draft_round_id=round.pk,
                tournament_name=self.tournament.name,
            )
            round.delete()

        options = self.tournament.get_draft_options(fresh=True)
        self.reset_timer_state(options, teams)

        # Delegate to shuffle module for shuffle style
        if self.draft_style == "shuffle":
            # Cycle: draft.services.shuffle imports draft.models.
            from draft.services.shuffle import build_shuffle_rounds

            build_shuffle_rounds(self, teams)
            if self.state == TeamDraftState.PENDING:
                self._emit_lobby_opened(options)
            return

        teams = list(teams)
        if not teams:
            log.error(
                "no_teams_found",
                system="tournament",
                subsystem="draft",
                tournament_id=self.tournament_id,
            )
            return

        num_teams = len(teams)
        picks_per_team = 4  # Each team picks 4 players after captain
        total_picks = num_teams * picks_per_team

        pick_number = 1
        phase = 1

        def create_draft_round(
            draft: "Draft", captain: CustomUser, pick_num: int, phase_num: int
        ) -> bool:
            try:
                draft_round = DraftRound.objects.create(
                    draft=draft,
                    captain=captain,
                    pick_number=pick_num,
                    pick_phase=phase_num,
                )
                log.debug(
                    "draft_round_created",
                    system="tournament",
                    subsystem="draft",
                    draft_round_id=draft_round.pk,
                    username=captain.username,
                    pick_phase=phase_num,
                    pick_number=pick_num,
                )
                return True
            except IntegrityError:
                log.error(
                    "draft_round_integrity_error",
                    system="tournament",
                    subsystem="draft",
                    username=captain.username,
                    pick_phase=phase_num,
                    pick_number=pick_num,
                )
                return False

        # Generate draft order based on style
        for round_num in range(picks_per_team):
            if self.draft_style == "snake":
                # Snake draft: alternate direction each round
                if round_num % 2 == 0:
                    # Forward: 1st, 2nd, 3rd, 4th team
                    pick_order = teams
                else:
                    # Reverse: 4th, 3rd, 2nd, 1st team
                    pick_order = list(reversed(teams))
            else:  # normal draft
                # Normal draft: always same order
                pick_order = teams

            # Create draft rounds for this phase
            for team in pick_order:
                if pick_number <= total_picks:
                    create_draft_round(self, team.captain, pick_number, phase)
                    pick_number += 1

            # Increment phase after all teams have picked
            phase += 1

        log.debug(
            "build_rounds_complete",
            system="tournament",
            subsystem="draft",
            rounds_created=pick_number - 1,
            tournament_name=self.tournament.name,
        )
        self.save()
        if self.state == TeamDraftState.PENDING:
            self._emit_lobby_opened(options)
        else:
            # Without a lobby event nothing tells open clients the rounds were rebuilt.
            self._emit_draft_started(num_teams)

    def go_back(self) -> bool:
        """
        Go back to the previous draft round.
        This method should be called when a captain wants to undo their last pick.
        """
        last_round = self.draft_rounds.last()
        if last_round:
            last_round.delete()
            return True
        return False

    def roll_until_winner(
        self, tied_teams: Iterable[Team]
    ) -> tuple[Team, list[list[dict[str, int]]]]:
        """
        Roll dice until exactly one winner emerges.

        Args:
            tied_teams: List of Team objects that are tied

        Returns:
            tuple: (winner_team, roll_rounds) where roll_rounds is a list of
                   lists containing {team_id, roll} dicts for each round
        """
        roll_rounds = []
        remaining = list(tied_teams)

        while len(remaining) > 1:
            rolls = [{"team_id": t.id, "roll": random.randint(1, 6)} for t in remaining]
            roll_rounds.append(rolls)

            max_roll = max(r["roll"] for r in rolls)
            remaining = [
                t
                for t in remaining
                if next(r["roll"] for r in rolls if r["team_id"] == t.id) == max_roll
            ]

        return remaining[0], roll_rounds

    def create_next_shuffle_round(
        self,
    ) -> "dict[str, DraftRound | int | dict[str, object] | None]":
        """
        Calculate which team picks next based on lowest total MMR.
        Creates a new DraftRound for the next pick.

        Returns:
            dict with keys:
            - round: The created DraftRound
            - team_mmr: The MMR of the team that will pick
            - tie_resolution: Dict with tie info if a tie occurred, else None
        """
        teams = list(self.teams)

        if not teams:
            raise ValueError("No teams in tournament")

        # Cycle: draft.services.shuffle imports draft.models.
        from draft.services.shuffle import get_team_total_mmr

        # Get organization for MMR lookups
        org = None
        if self.tournament.league:
            org = self.tournament.league.organization

        # Calculate current total MMR for each team
        team_mmrs = []
        for team in teams:
            total = get_team_total_mmr(team, organization=org)
            team_mmrs.append({"team": team, "mmr": total})

        # Find lowest MMR
        min_mmr = min(t["mmr"] for t in team_mmrs)
        tied_teams_data = [t for t in team_mmrs if t["mmr"] == min_mmr]

        # Handle tie with random rolls
        tie_resolution = None
        if len(tied_teams_data) > 1:
            tied_teams = [t["team"] for t in tied_teams_data]
            winner, roll_rounds = self.roll_until_winner(tied_teams)
            tie_resolution = {
                "tied_teams": [
                    {"id": t["team"].id, "name": t["team"].name, "mmr": t["mmr"]}
                    for t in tied_teams_data
                ],
                "roll_rounds": roll_rounds,
                "winner_id": winner.id,
            }
            next_team = winner
            next_mmr = next(
                t["mmr"] for t in tied_teams_data if t["team"].id == winner.id
            )
        else:
            next_team = tied_teams_data[0]["team"]
            next_mmr = tied_teams_data[0]["mmr"]

        # Create the DraftRound
        pick_number = self.draft_rounds.count() + 1
        num_teams = len(teams)
        phase = (pick_number - 1) // num_teams + 1

        draft_round = DraftRound.objects.create(
            draft=self,
            captain=next_team.captain,
            pick_number=pick_number,
            pick_phase=phase,
            was_tie=bool(tie_resolution),
            tie_roll_data=tie_resolution,
        )

        return {
            "round": draft_round,
            "team_mmr": next_mmr,
            "tie_resolution": tie_resolution,
        }


class DraftRound(models.Model):
    draft = models.ForeignKey(
        Draft,
        related_name="draft_rounds",
        on_delete=models.CASCADE,
    )
    captain = models.ForeignKey(
        User,
        related_name="draft_rounds_captained",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
    )
    pick_number = models.IntegerField(
        default=1,
        blank=True,
        help_text="pick number starts at 1, and counts all picks",
    )
    pick_phase = models.IntegerField(
        default=1,
        blank=True,
        help_text="pick phase is only increase after all captains have picked once",
    )

    choice = models.ForeignKey(
        User,
        related_name="draftrounds_choice",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )

    # Tie tracking fields for shuffle draft mode
    was_tie = models.BooleanField(
        default=False,
        help_text="Whether this round was determined by a tie-breaker roll",
    )
    tie_roll_data = models.JSONField(
        null=True,
        blank=True,
        help_text="Stores tie resolution: {tied_teams, roll_rounds, winner_id}",
    )

    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    timed_out_at = models.DateTimeField(null=True, blank=True)
    grace_time_ms = models.IntegerField(null=True, blank=True)
    pick_duration_ms = models.IntegerField(null=True, blank=True)
    reserve_used_ms = models.IntegerField(null=True, blank=True)
    skip_count = models.IntegerField(default=0)

    class Meta:
        ordering = ["pick_number"]
        db_table = "app_draftround"

    def save(self, *args: object, **kwargs: object) -> None:
        super().save(*args, **kwargs)
        # Invalidate specific tournament and draft when picks are made
        # Use invalidate_obj() to avoid invalidating ALL tournaments/drafts

        if self.draft:
            invalidate_obj(self.draft)
            if self.draft.tournament:
                invalidate_obj(self.draft.tournament)

    @property
    def team(self) -> "Team | None":
        if not self.draft:
            raise ValueError("Draft must be associated with a draft.")

        tournament = self.draft.tournament
        prefetched = getattr(tournament, "_prefetched_objects_cache", {}).get("teams")
        if prefetched is not None:
            matches = [t for t in prefetched if t.captain_id == self.captain_id]
            return min(matches, key=lambda t: t.pk) if matches else None

        return Team.objects.filter(
            tournament=self.draft.tournament, captain=self.captain
        ).first()

    def pick_player(self, user: CustomUser) -> None:
        if self.choice:
            raise ValueError("This draft round already has a choice.")

        captain_name = self.captain.username if self.captain else "unassigned"
        log.debug(
            "draft_round_pick_started",
            system="tournament",
            subsystem="draft",
            draft_round_id=self.pk,
            username=user.username,
            captain_name=captain_name,
        )
        remaining = self.draft.users_remaining
        if remaining.filter(id=user.id).exists():
            self.choice = user
            team = self.team
            if team:
                team.members.add(user)
                team.save()
            self.save()  # This triggers cache invalidation
            log.debug(
                "draft_pick_success",
                system="tournament",
                subsystem="draft",
                username=user.username,
                draft_round_id=self.pk,
            )
        else:
            available_users = list(remaining.values_list("username", flat=True))
            log.error(
                "draft_pick_user_unavailable",
                system="tournament",
                subsystem="draft",
                username=user.username,
                available_usernames=available_users,
            )
            raise ValueError("User is not available for drafting.")

    def __str__(self) -> str:
        captain_name = self.captain.username if self.captain else "unassigned"
        choice_name = self.choice.username if self.choice else "pending"
        tournament_name = (
            self.draft.tournament.name
            if self.draft and self.draft.tournament
            else "unknown"
        )
        return f"{captain_name} picked {choice_name} in {tournament_name}"


class DraftEvent(models.Model):
    """Tracks draft lifecycle events for history and WebSocket broadcast."""

    EVENT_TYPE_CHOICES = [
        ("draft_started", "Draft Started"),
        ("draft_completed", "Draft Completed"),
        ("captain_assigned", "Captain Assigned"),
        ("player_picked", "Player Picked"),
        ("tie_roll", "Tie Roll"),
        ("pick_undone", "Pick Undone"),
        ("draft_lobby_opened", "Draft Lobby Opened"),
        ("captain_ready", "Captain Ready"),
        ("captain_unready", "Captain Unready"),
        ("captain_connected", "Captain Connected"),
        ("captain_disconnected", "Captain Disconnected"),
        ("draft_started_by_staff", "Draft Started By Staff"),
        ("draft_force_started", "Draft Force Started"),
        ("round_started", "Round Started"),
        ("draft_paused", "Draft Paused"),
        ("draft_resumed", "Draft Resumed"),
        ("pick_timed_out", "Pick Timed Out"),
        ("pick_skipped", "Pick Skipped"),
        ("pick_skip_unavailable", "Pick Skip Unavailable"),
        ("draft_options_changed", "Draft Options Changed"),
        ("team_changed", "Team Changed"),
    ]

    draft = models.ForeignKey(
        Draft,
        related_name="events",
        on_delete=models.CASCADE,
    )
    event_type = models.CharField(
        max_length=32,
        choices=EVENT_TYPE_CHOICES,
    )
    payload = models.JSONField(
        default=dict,
        help_text="Event-specific data (JSON)",
    )
    actor = models.ForeignKey(
        User,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="draft_events_triggered",
        help_text="User who triggered this event",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        db_table = "app_draftevent"

    def __str__(self) -> str:
        return f"{self.event_type} - Draft {self.draft_id} at {self.created_at}"


class DraftOptions(models.Model):
    tournament = models.OneToOneField(
        "app.Tournament",
        related_name="draft_options",
        on_delete=models.CASCADE,
    )
    timer_enabled = models.BooleanField(default=True)
    grace_time_ms = models.IntegerField(default=30000)
    reserve_time_ms = models.IntegerField(default=30000)
    timeout_action = models.CharField(
        max_length=32,
        choices=TimeoutAction.choices,
        default=TimeoutAction.SKIP_TURN,
    )
    hero_timer_enabled = models.BooleanField(default=True)
    hero_grace_time_ms = models.IntegerField(default=30000)
    hero_reserve_time_ms = models.IntegerField(default=90000)

    class Meta:
        db_table = "app_draftoptions"

    def __str__(self) -> str:
        return f"DraftOptions for tournament {self.tournament_id}"

    def save(self, *args: object, **kwargs: object) -> None:
        super().save(*args, **kwargs)
        invalidate_obj(self.tournament)

    @classmethod
    def ensure_for(
        cls,
        tournament: Tournament,
        *,
        timer_enabled: bool | None = None,
        grace_time_ms: int | None = None,
        reserve_time_ms: int | None = None,
    ) -> "DraftOptions":
        provided = {
            "timer_enabled": timer_enabled,
            "grace_time_ms": grace_time_ms,
            "reserve_time_ms": reserve_time_ms,
        }
        defaults = {k: v for k, v in provided.items() if v is not None}
        options, _ = cls.objects.update_or_create(
            tournament=tournament, defaults=defaults
        )
        return options
