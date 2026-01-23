import logging

import nh3
import requests
from cacheops import cached_as, invalidate_model
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from django.db.utils import IntegrityError
from django.utils import timezone
from social_django.models import USER_MODEL  # fix: skip
from social_django.models import AbstractUserSocialAuth, DjangoStorage

User = settings.AUTH_USER_MODEL

from enum import IntEnum, StrEnum

from django.contrib.auth.models import AbstractUser
from django.db.models import JSONField

log = logging.getLogger(__name__)


class PositionsModel(models.Model):
    carry = models.IntegerField(
        default=0,
        help_text="Rank of the carry position from 0 (No play) to 5 (best)",
    )
    mid = models.IntegerField(
        default=0, help_text="Rank of the mid position from 0 (No play) to 5 (best)"
    )
    offlane = models.IntegerField(
        default=0,
        help_text="Rank of the offlane position from 0 (No play) to 5 (best)",
    )
    soft_support = models.IntegerField(
        default=0,
        help_text="Rank of the soft support position from 0 (No play) to 5 (best)",
    )
    hard_support = models.IntegerField(
        default=0,
        help_text="Rank of the hard support position from 0 (No play) to 5 (best)",
    )

    def __str__(self):
        return f"Carry: {self.carry}, Mid: {self.mid}, Offlane: {self.offlane}, Soft Support: {self.soft_support}, Hard Support: {self.hard_support}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Invalidate CustomUser cache since positions are embedded in user serializations
        from cacheops import invalidate_model

        invalidate_model(CustomUser)


# Enum for Dota2 positions
class PositionEnum(IntEnum):
    Carry = 1
    Mid = 2
    Offlane = 3
    SoftSupport = 4
    HardSupport = 5


# Enum for Dota2 positions
class DraftStyles(StrEnum):
    snake = "snake"
    normal = "normal"
    shuffle = "shuffle"


class CustomUser(AbstractUser):
    steamid = models.IntegerField(null=True, unique=True, blank=True)
    nickname = models.TextField(null=True, blank=True)
    mmr = models.IntegerField(null=True, blank=True)
    league_mmr = models.IntegerField(null=True, blank=True)

    # MMR verification tracking
    has_active_dota_mmr = models.BooleanField(default=False)
    dota_mmr_last_verified = models.DateTimeField(null=True, blank=True)

    @property
    def needs_mmr_verification(self) -> bool:
        """Check if user needs to verify their MMR (>30 days since last verification)."""
        if not self.has_active_dota_mmr:
            return False
        if self.dota_mmr_last_verified is None:
            return True
        days_since = (timezone.now() - self.dota_mmr_last_verified).days
        return days_since > 30

    # Store positions as a dict of 1-5: bool, e.g. {"1": true, "2": false, ...}
    positions = models.ForeignKey(
        PositionsModel,
        on_delete=models.CASCADE,
        help_text="Positions field",
        null=False,
        blank=True,
    )
    avatar = models.TextField(null=True, blank=True)
    discordId = models.TextField(null=True, unique=True, blank=True)
    discordUsername = models.TextField(null=True, blank=True)
    discordNickname = models.TextField(null=True, blank=True)
    guildNickname = models.TextField(null=True, blank=True)
    default_organization = models.ForeignKey(
        "Organization",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="default_for_users",
    )

    # Steam ID conversion constant
    # Steam64 (Friend ID) = 76561197960265728 + Steam32 (Account ID)
    STEAM_ID_64_BASE = 76561197960265728

    @property
    def steam_account_id(self):
        """
        Returns the 32-bit Steam Account ID computed from the 64-bit Friend ID.

        Steam uses two ID formats:
        - Steam64/Friend ID: Used in Steam Community URLs (e.g., 76561198012345678)
        - Steam32/Account ID: Used in match data from Steam API (e.g., 52079950)

        Conversion: Account ID = Friend ID - 76561197960265728
        """
        if self.steamid is None:
            return None
        return self.steamid - self.STEAM_ID_64_BASE

    def createFromDiscordData(self, data):
        self.username = data["user"]["username"]
        self.discordId = data["user"]["id"]
        self.avatar = data["user"]["avatar"]
        self.discordUsername = data["user"]["username"]
        self.nickname = data.get("nick", "")
        return self

    def check_and_update_avatar(self):
        """
        Checks if the current avatar URL is valid. If not, fetches the latest
        avatar from Discord and updates the database.

        Returns:
            bool: True if the avatar was updated, False otherwise.
        """
        if not self.discordId:
            return False

        if not self.avatar:
            # If no avatar is set, try to fetch one.
            return self._fetch_and_update_avatar_from_discord()

        # Construct current avatar URL
        extension = "gif" if self.avatar.startswith("a_") else "png"
        current_url = f"https://cdn.discordapp.com/avatars/{self.discordId}/{self.avatar}.{extension}"

        if self._is_avatar_url_valid(current_url):
            return False

        return self._fetch_and_update_avatar_from_discord()

    def _is_avatar_url_valid(self, url):
        """
        Check if the avatar URL returns a valid response (not 404).
        """
        try:
            response = requests.head(url, timeout=5)
            return response.status_code == 200
        except requests.RequestException:
            logging.warning(
                f"Failed to validate avatar URL for user {self.username}: {url}"
            )
            return False

    def _fetch_and_update_avatar_from_discord(self):
        """
        Fetch the latest avatar from Discord API and update the database.

        Returns:
            bool: True if avatar was updated, False otherwise.
        """
        if not self.discordId:
            return False

        # Skip if Discord bot token is not configured (e.g., in CI)
        discord_bot_token = getattr(settings, "DISCORD_BOT_TOKEN", None)
        if not discord_bot_token:
            logging.debug(
                f"Skipping avatar fetch for {self.username}: DISCORD_BOT_TOKEN not configured"
            )
            return False

        try:
            headers = {
                "Authorization": f"Bot {discord_bot_token}",
            }
            response = requests.get(
                f"{settings.DISCORD_API_BASE_URL}/users/{self.discordId}",
                headers=headers,
                timeout=10,
            )

            if response.status_code == 200:
                user_data = response.json()
                new_avatar = user_data.get("avatar")

                if new_avatar != self.avatar:
                    self.avatar = new_avatar
                    self.save(update_fields=["avatar"])
                    logging.info(
                        f"Updated avatar for user {self.username} (Discord ID: {self.discordId})"
                    )
                    return True
                return False

            else:
                logging.warning(
                    f"Failed to fetch Discord user data for {self.username}: {response.status_code}"
                )
                return False

        except requests.RequestException as e:
            logging.error(
                f"Error fetching Discord avatar for user {self.username}: {str(e)}"
            )
            return False
        except Exception as e:
            logging.error(
                f"Unexpected error updating avatar for user {self.username}: {str(e)}"
            )
            return False

    def save(self, *args, **kwargs):
        """
        Override save method to automatically create a PositionsModel instance
        if the user doesn't have one, and invalidate dependent caches.
        """
        if not self.positions_id:  # Check if positions is not set
            # Create a default PositionsModel with all positions set to 0
            default_positions = PositionsModel.objects.create()
            self.positions = default_positions

        super().save(*args, **kwargs)

        # Invalidate caches that depend on CustomUser
        from cacheops import invalidate_model

        invalidate_model(CustomUser)

    @property
    def avatarUrl(self):
        """
        Constructs the Discord avatar URL from the stored discordId and avatar hash.
        This property does not perform any network requests.
        """
        if not self.discordId:
            return None

        if self.avatar:
            extension = "gif" if self.avatar.startswith("a_") else "png"
            return f"https://cdn.discordapp.com/avatars/{self.discordId}/{self.avatar}.{extension}"

        # Default avatar logic
        if self.discordId:
            # New default avatar URL logic based on user ID
            return f"https://cdn.discordapp.com/embed/avatars/{(int(self.discordId) >> 22) % 6}.png"

        return f"https://cdn.discordapp.com/embed/avatars/0.png"  # Fallback


class Organization(models.Model):
    """Organization that owns leagues and tournaments."""

    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="", max_length=10000)
    logo = models.URLField(blank=True, default="")
    discord_link = models.URLField(blank=True, default="")
    rules_template = models.TextField(blank=True, default="", max_length=50000)
    admins = models.ManyToManyField(
        "CustomUser",
        related_name="admin_organizations",
        blank=True,
    )
    staff = models.ManyToManyField(
        "CustomUser",
        related_name="staff_organizations",
        blank=True,
    )
    default_league = models.ForeignKey(
        "League",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="default_for_organization",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]
        verbose_name = "Organization"
        verbose_name_plural = "Organizations"

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Invalidate Organization cache when modified
        invalidate_model(Organization)

    def delete(self, *args, **kwargs):
        # Invalidate caches before deletion
        invalidate_model(Organization)
        invalidate_model(League)
        super().delete(*args, **kwargs)


class League(models.Model):
    """League that belongs to an organization, 1:1 with Steam league."""

    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name="leagues",
    )
    steam_league_id = models.IntegerField(unique=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True, default="", max_length=10000)
    rules = models.TextField(blank=True, default="", max_length=50000)
    prize_pool = models.CharField(max_length=100, blank=True, default="")
    admins = models.ManyToManyField(
        "CustomUser",
        related_name="admin_leagues",
        blank=True,
    )
    staff = models.ManyToManyField(
        "CustomUser",
        related_name="staff_leagues",
        blank=True,
    )
    last_synced = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Rating system configuration
    RATING_SYSTEM_CHOICES = [
        ("elo", "Elo"),
        ("fixed_delta", "Fixed Delta"),
    ]
    rating_system = models.CharField(
        max_length=20,
        choices=RATING_SYSTEM_CHOICES,
        default="elo",
        help_text="Rating calculation method",
    )
    k_factor_default = models.FloatField(
        default=32.0,
        help_text="Default K-factor for Elo calculations",
    )
    k_factor_placement = models.FloatField(
        default=64.0,
        help_text="K-factor for players in placement games",
    )
    placement_games = models.PositiveIntegerField(
        default=10,
        help_text="Number of placement games before using default K-factor",
    )
    fixed_delta = models.FloatField(
        default=25.0,
        help_text="Fixed rating change per game (for fixed_delta system)",
    )

    # Age decay configuration
    age_decay_enabled = models.BooleanField(
        default=False,
        help_text="Enable age-based decay for older matches",
    )
    age_decay_half_life_days = models.PositiveIntegerField(
        default=180,
        help_text="Half-life in days for age decay calculation",
    )
    age_decay_minimum = models.FloatField(
        default=0.1,
        help_text="Minimum decay factor (0.0-1.0)",
    )

    # Recalculation constraints
    recalc_max_age_days = models.PositiveIntegerField(
        default=90,
        help_text="Maximum age in days for match recalculation",
    )
    recalc_mmr_threshold = models.PositiveIntegerField(
        default=500,
        help_text="Maximum MMR change allowed for recalculation",
    )

    class Meta:
        ordering = ["name"]
        verbose_name = "League"
        verbose_name_plural = "Leagues"

    def __str__(self):
        return f"{self.name} ({self.steam_league_id})"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Invalidate League cache and Organization cache
        # (Organization has league_count annotation that depends on leagues)
        invalidate_model(League)
        invalidate_model(Organization)

    def delete(self, *args, **kwargs):
        # Invalidate caches before deletion
        invalidate_model(League)
        invalidate_model(Organization)
        super().delete(*args, **kwargs)


TOURNAMNET_TYPE_CHOICES = [
    ("single_elimination", "Single Elimination"),
    ("double_elimination", "Double Elimination"),
    ("swiss", "Swiss Bracket"),
]


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
    # Removed teams field; handled by ForeignKey in Team
    winning_team = models.OneToOneField(
        "Team",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tournaments_won",
    )

    state = models.CharField(max_length=20, choices=STATE_CHOICES, default="future")
    tournament_type = models.CharField(
        max_length=20, choices=TOURNAMNET_TYPE_CHOICES, default="double_elimination"
    )

    steam_league_id = models.IntegerField(
        null=True,
        blank=True,
        default=settings.DEFAULT_LEAGUE_ID,
        help_text="Steam league ID for match linking",
        db_column="league_id",  # Keep existing column name for backwards compatibility
    )
    league = models.ForeignKey(
        "League",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="tournaments",
        db_column="league_fk_id",
    )

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Invalidate Tournament cache and related caches
        # (Organization has tournament_count annotation that depends on tournaments via leagues)
        invalidate_model(Tournament)
        invalidate_model(League)
        invalidate_model(Organization)

    @property
    def captains(self):
        """
        Returns all users who are captains in this tournament.
        This is used to populate the draft choices.
        """
        if not self.users.exists():
            return []
        if not self.teams.exists():
            return []
        return self.users.filter(teams_as_captain__tournament=self).distinct()


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

    current_points = models.IntegerField(default=0, blank=True)
    placement = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        help_text="Final tournament placement (1=winner, 2=runner-up, etc.)",
    )

    def __str__(self):
        return self.name

    @property
    def games(self):
        return Game.objects.filter(
            models.Q(radiant_team=self) | models.Q(dire_team=self)
        )


class Game(models.Model):
    tournament = models.ForeignKey(
        Tournament,
        related_name="games",
        on_delete=models.CASCADE,
        null=True,
        blank=True,  # Now optional
    )
    league = models.ForeignKey(
        "League",
        related_name="games",
        on_delete=models.CASCADE,
        null=True,
        blank=True,  # Games can belong directly to a league
    )
    round = models.IntegerField(default=1)

    # Bracket positioning fields
    bracket_type = models.CharField(
        max_length=20,
        choices=[
            ("winners", "Winners Bracket"),
            ("losers", "Losers Bracket"),
            ("grand_finals", "Grand Finals"),
            ("swiss", "Swiss"),
        ],
        default="winners",
    )
    elimination_type = models.CharField(
        max_length=10,
        choices=[
            ("single", "Single Elimination"),
            ("double", "Double Elimination"),
            ("swiss", "Swiss"),
        ],
        default="double",
        help_text="single=loser out, double=loser drops to losers bracket, swiss=record-based",
    )
    position = models.IntegerField(
        default=0, help_text="Position within round (0-indexed)"
    )

    # Match flow - which game winner advances to
    next_game = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="source_games",
    )
    next_game_slot = models.CharField(
        max_length=10,
        choices=[("radiant", "Radiant"), ("dire", "Dire")],
        null=True,
        blank=True,
    )

    # Loser path (for double elimination)
    loser_next_game = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="loser_source_games",
        help_text="Game where loser advances to (for double elim rounds)",
    )
    loser_next_game_slot = models.CharField(
        max_length=10,
        choices=[("radiant", "Radiant"), ("dire", "Dire")],
        null=True,
        blank=True,
    )

    # Swiss format tracking
    swiss_record_wins = models.IntegerField(
        default=0, help_text="Team's wins entering this match (Swiss format)"
    )
    swiss_record_losses = models.IntegerField(
        default=0, help_text="Team's losses entering this match (Swiss format)"
    )

    # Match status
    status = models.CharField(
        max_length=20,
        choices=[
            ("pending", "Pending"),
            ("live", "Live"),
            ("completed", "Completed"),
        ],
        default="pending",
    )

    # steam gameid if it exists
    gameid = models.IntegerField(null=True, blank=True)

    radiant_team = models.ForeignKey(
        Team,
        related_name="games_as_radiant",
        null=True,
        on_delete=models.CASCADE,
        blank=True,
    )
    dire_team = models.ForeignKey(
        Team,
        related_name="games_as_dire",
        null=True,
        on_delete=models.CASCADE,
        blank=True,
    )
    winning_team = models.ForeignKey(
        Team, related_name="games_won", null=True, on_delete=models.CASCADE, blank=True
    )

    def __str__(self):
        tourn_name = self.tournament.name if self.tournament else "No Tournament"
        radiant = self.radiant_team.name if self.radiant_team else "TBD"
        dire = self.dire_team.name if self.dire_team else "TBD"
        return f"{radiant} vs {dire} in {tourn_name}"

    @property
    def teams(self):
        return [self.radiant_team, self.dire_team]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Invalidate tournament, league, and team caches when games are modified
        from cacheops import invalidate_model, invalidate_obj

        if self.tournament_id:
            invalidate_obj(self.tournament)
        if self.league_id:
            invalidate_obj(self.league)
        invalidate_model(Team)


from cacheops import cached_as


class Draft(models.Model):

    tournament = models.OneToOneField(
        Tournament,
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

    def __str__(self):
        return f"Draft {self.pk} in {self.tournament.name}"

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Invalidate tournament cache when draft are made
        from cacheops import invalidate_model, invalidate_obj

        invalidate_obj(self.tournament)

    def _simulate_draft(self, draft_style="snake"):
        """
        Simulate a draft where each captain picks the highest MMR player available.
        Returns a dict with team_id -> list of picked players (including captain).

        Args:
            draft_style: "snake" or "normal"
        """

        def get_simulation_data(draft_style=draft_style):
            teams = list(self.tournament.teams.order_by("draft_order"))
            log.debug(f"Getting Simulation for {draft_style} teams: {teams}")
            if not teams:
                return {}

            # Get all available players (excluding captains) sorted by MMR desc
            available_players = list(
                self.tournament.users.exclude(
                    teams_as_captain__tournament=self.tournament
                )
                .order_by("-mmr")
                .values_list("id", "mmr")
            )

            # Initialize team rosters with captains
            team_rosters = {}
            for team in teams:
                captain_mmr = team.captain.mmr or 0
                team_rosters[team.id] = [(team.captain.id, captain_mmr)]

            # Simulate draft rounds (4 picks per team after captain)
            picks_per_team = 4
            num_teams = len(teams)
            total_picks = num_teams * picks_per_team
            pick_number = 1
            phase = 1

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
                            f"{draft_style} sim: Team {team.name} picked player {player_id} with MMR {player_mmr}"
                        )
                        pick_number += 1

            return team_rosters

        data = get_simulation_data(draft_style=draft_style)
        log.debug(data)
        return data

    @property
    def snake_first_pick_mmr(self):
        """Calculate total MMR for first pick team in snake draft simulation."""
        simulation = self._simulate_draft("snake")
        if not simulation:
            return 0

        # First team in draft order
        first_team = self.tournament.teams.order_by("draft_order").first()
        if not first_team or first_team.id not in simulation:
            return 0
        return sum(mmr for _, mmr in simulation[first_team.id])

    @property
    def snake_last_pick_mmr(self):
        """Calculate total MMR for last pick team in snake draft simulation."""
        simulation = self._simulate_draft("snake")
        if not simulation:
            return 0

        # Last team in draft order
        last_team = self.tournament.teams.order_by("draft_order").last()
        if not last_team or last_team.id not in simulation:
            return 0

        return sum(mmr for _, mmr in simulation[last_team.id])

    @property
    def normal_first_pick_mmr(self):
        """Calculate total MMR for first pick team in normal draft simulation."""
        simulation = self._simulate_draft("normal")
        if not simulation:
            return 0

        # First team in draft order
        first_team = self.tournament.teams.order_by("draft_order").first()
        if not first_team or first_team.id not in simulation:
            return 0

        return sum(mmr for _, mmr in simulation[first_team.id])

    @property
    def normal_last_pick_mmr(self):
        """Calculate total MMR for last pick team in normal draft simulation."""
        simulation = self._simulate_draft("normal")
        if not simulation:
            return 0

        # Last team in draft order
        last_team = self.tournament.teams.order_by("draft_order").last()
        if not last_team or last_team.id not in simulation:
            return 0

        return sum(mmr for _, mmr in simulation[last_team.id])

    @property
    def current_draft_first_pick_mmr(self):
        """Calculate total MMR for first pick team using current draft style."""
        simulation = self._simulate_draft(self.draft_style)
        if not simulation:
            return 0

        first_team = self.tournament.teams.order_by("draft_order").first()
        if not first_team or first_team.id not in simulation:
            return 0

        return sum(mmr for _, mmr in simulation[first_team.id])

    @property
    def current_draft_last_pick_mmr(self):
        """Calculate total MMR for last pick team using current draft style."""
        simulation = self._simulate_draft(self.draft_style)
        if not simulation:
            return 0

        last_team = self.tournament.teams.order_by("draft_order").last()
        if not last_team or last_team.id not in simulation:
            return 0

        return sum(mmr for _, mmr in simulation[last_team.id])

    @property
    def teams(self):
        if not self.tournament.teams.exists():
            return []

        return self.tournament.teams.all()

    @property
    def users(self):
        if not self.tournament.users.exists():
            return []

        return self.tournament.users.all()

    @property
    def users_remaining(self):
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
        log.debug(f"Picked user IDs: {list(picked_user_ids)}")
        captain_ids = list(
            self.tournament.teams.filter(captain__isnull=False).values_list(
                "captain_id", flat=True
            )
        )
        log.debug(f"Captain IDs: {captain_ids}")
        excluded_ids = set(picked_user_ids + captain_ids)
        log.debug(f"All excluded IDs: {excluded_ids}")
        users = self.tournament.users.exclude(id__in=excluded_ids).distinct()

        log.debug(f"Users remaining: {[user.pk for user in users ]}")
        return users

    @property
    def captains(self):
        if not self.tournament.captains.exists():
            raise ValueError("Draft must be associated with a tournament.")

        return self.tournament.captains.all()

    @property
    def latest_round(self):
        """
        Returns the latest draft round.
        """
        if not self.draft_rounds.exists():
            log.error("No draft rounds exist")
            return

        latest_round = (
            self.draft_rounds.order_by("pick_number")
            .exclude(choice__isnull=False)
            .first()
        )
        if not latest_round:
            latest_round = self.draft_rounds.order_by("pick_number").last()

        return latest_round.pk

    def rebuild_teams(self):
        """
        Build teams based on the draft choices.
        This method should be called after all draft rounds are completed.
        """
        logging.debug(f"Creating draft round for {self.tournament.name} ")
        if not self.tournament:
            raise ValueError("Draft must be associated with a tournament.")

        if not self.tournament.captains:
            raise ValueError("Draft must have captains to build teams.")
        logging.debug(f"Creating draft round 2 for {self.tournament.name} ")
        for team in self.tournament.teams.all():
            logging.debug(
                f"Rebuilding team {team.name} for tournament {self.tournament.name}"
            )
            team.members.clear()
            team.members.add(team.captain)

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
                logging.debug(
                    f"Rebuild_TEAMS: Creating draft round for {team.name} for tournament {self.tournament.name}"
                )
                team.members.add(draft_round.choice)
                team.save()

    def build_rounds(self):
        logging.debug(f"Building draft rounds with style: {self.draft_style}")

        # Clear existing draft rounds
        for round in self.draft_rounds.all():
            logging.debug(
                f"Draft round {round.pk} already exists for {self.tournament.name}"
            )
            round.delete()

        # Delegate to shuffle module for shuffle style
        if self.draft_style == "shuffle":
            from app.functions.shuffle_draft import build_shuffle_rounds

            build_shuffle_rounds(self)
            return

        teams = list(self.tournament.teams.order_by("draft_order"))
        if not teams:
            logging.error("No teams found for tournament")
            return

        num_teams = len(teams)
        picks_per_team = 4  # Each team picks 4 players after captain
        total_picks = num_teams * picks_per_team

        pick_number = 1
        phase = 1

        def create_draft_round(draft, captain, pick_num, phase_num):
            try:
                draft_round = DraftRound.objects.create(
                    draft=draft,
                    captain=captain,
                    pick_number=pick_num,
                    pick_phase=phase_num,
                )
                logging.debug(
                    f"Draft round {draft_round.pk} created for {captain.username} "
                    f"in phase {phase_num}, pick {pick_num}"
                )
                return True
            except IntegrityError:
                logging.error(
                    f"IntegrityError: Draft round already exists for {captain.username} "
                    f"in phase {phase_num}, pick {pick_num}"
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

        logging.debug(
            f"Created {pick_number - 1} draft rounds for {self.tournament.name}"
        )
        self.save()

    def go_back(self):
        """
        Go back to the previous draft round.
        This method should be called when a captain wants to undo their last pick.
        """
        last_round = self.draft_rounds.last()
        if last_round:
            last_round.delete()
            return True
        return False

    def roll_until_winner(self, tied_teams):
        """
        Roll dice until exactly one winner emerges.

        Args:
            tied_teams: List of Team objects that are tied

        Returns:
            tuple: (winner_team, roll_rounds) where roll_rounds is a list of
                   lists containing {team_id, roll} dicts for each round
        """
        import random

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

    def create_next_shuffle_round(self):
        """
        Calculate which team picks next based on lowest total MMR.
        Creates a new DraftRound for the next pick.

        Returns:
            dict with keys:
            - round: The created DraftRound
            - team_mmr: The MMR of the team that will pick
            - tie_resolution: Dict with tie info if a tie occurred, else None
        """
        teams = list(self.tournament.teams.all())

        if not teams:
            raise ValueError("No teams in tournament")

        # Calculate current total MMR for each team
        team_mmrs = []
        for team in teams:
            total = team.captain.mmr or 0
            for member in team.members.exclude(id=team.captain_id):
                total += member.mmr or 0
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

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        # Invalidate tournament cache when draft picks are made
        from cacheops import invalidate_model, invalidate_obj

        invalidate_obj(self.draft.tournament)
        invalidate_obj(self.draft)

        invalidate_model(Tournament)
        invalidate_model(Draft)
        invalidate_model(Team)

    @property
    def team(self):
        if not self.draft:
            raise ValueError("Draft must be associated with a draft.")

        return Team.objects.filter(
            tournament=self.draft.tournament, captain=self.captain
        ).first()

    def pick_player(self, user: CustomUser):
        if self.choice:
            raise ValueError("This draft round already has a choice.")

        captain_name = self.captain.username if self.captain else "unassigned"
        log.debug(
            f"Draft round {self.pk} picking player {user.username} for captain {captain_name}"
        )
        log.debug(self.draft.users_remaining)

        # Debug the current state
        remaining_count_before = self.draft.users_remaining.count()
        log.debug(f"Users remaining before pick: {remaining_count_before}")

        if self.draft.users_remaining.filter(id=user.id).exists():
            self.choice = user
            team = self.team
            if team:
                team.members.add(user)
                team.save()
            self.save()  # This triggers cache invalidation

            remaining_count_after = self.draft.users_remaining.count()
            log.debug(f"Users remaining after pick: {remaining_count_after}")
            log.debug(f"Successfully picked {user.username}")
        else:
            available_users = list(
                self.draft.users_remaining.values_list("username", flat=True)
            )
            log.error(
                f"User {user.username} is not available. Available: {available_users}"
            )
            raise ValueError("User is not available for drafting.")

    def __str__(self):
        return f"{self.picker.username} picked {self.choice.username} in {self.tournament.name}"


class Joke(models.Model):
    """Tracks joke-related data per user (tangoes purchased, etc.)."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="joke")
    tangoes_purchased = models.IntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Joke"
        verbose_name_plural = "Jokes"

    def __str__(self):
        return f"{self.user.username} - {self.tangoes_purchased} tangoes"


class DraftEvent(models.Model):
    """Tracks draft lifecycle events for history and WebSocket broadcast."""

    EVENT_TYPE_CHOICES = [
        ("draft_started", "Draft Started"),
        ("draft_completed", "Draft Completed"),
        ("captain_assigned", "Captain Assigned"),
        ("player_picked", "Player Picked"),
        ("tie_roll", "Tie Roll"),
        ("pick_undone", "Pick Undone"),
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

    def __str__(self):
        return f"{self.event_type} - Draft {self.draft_id} at {self.created_at}"


class HeroDraftState(models.TextChoices):
    """State machine states for Captain's Mode hero draft."""

    WAITING_FOR_CAPTAINS = "waiting_for_captains", "Waiting for Captains"
    ROLLING = "rolling", "Rolling"
    CHOOSING = "choosing", "Choosing"
    DRAFTING = "drafting", "Drafting"
    PAUSED = "paused", "Paused"
    COMPLETED = "completed", "Completed"
    ABANDONED = "abandoned", "Abandoned"


class HeroDraft(models.Model):
    """Captain's Mode hero draft for a tournament game."""

    game = models.OneToOneField(
        "app.Game", on_delete=models.CASCADE, related_name="herodraft"
    )
    state = models.CharField(
        max_length=32,
        choices=HeroDraftState.choices,
        default=HeroDraftState.WAITING_FOR_CAPTAINS,
    )
    roll_winner = models.ForeignKey(
        "DraftTeam",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="won_rolls",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        invalidate_model(HeroDraft)

    def __str__(self):
        return f"HeroDraft for {self.game}"


class DraftTeam(models.Model):
    """One of the two teams in a hero draft."""

    draft = models.ForeignKey(
        HeroDraft, on_delete=models.CASCADE, related_name="draft_teams"
    )
    tournament_team = models.ForeignKey(
        "app.Team", on_delete=models.CASCADE, related_name="hero_draft_teams"
    )
    is_first_pick = models.BooleanField(null=True, blank=True)
    is_radiant = models.BooleanField(null=True, blank=True)
    reserve_time_remaining = models.IntegerField(default=90000)  # 90 seconds in ms
    is_ready = models.BooleanField(default=False)
    is_connected = models.BooleanField(default=False)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        invalidate_model(DraftTeam)

    @property
    def captain(self):
        return self.tournament_team.captain

    def __str__(self):
        return f"DraftTeam: {self.tournament_team} in {self.draft}"


class HeroDraftRound(models.Model):
    """A single pick or ban action in the draft."""

    ACTION_CHOICES = [
        ("ban", "Ban"),
        ("pick", "Pick"),
    ]

    STATE_CHOICES = [
        ("planned", "Planned"),
        ("active", "Active"),
        ("completed", "Completed"),
    ]

    draft = models.ForeignKey(
        HeroDraft, on_delete=models.CASCADE, related_name="rounds"
    )
    draft_team = models.ForeignKey(
        DraftTeam, on_delete=models.CASCADE, related_name="rounds"
    )
    round_number = models.IntegerField()
    action_type = models.CharField(max_length=8, choices=ACTION_CHOICES)
    hero_id = models.IntegerField(null=True, blank=True)
    state = models.CharField(max_length=16, choices=STATE_CHOICES, default="planned")
    grace_time_ms = models.IntegerField(default=30000)  # 30 seconds
    started_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["round_number"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        invalidate_model(HeroDraftRound)

    def __str__(self):
        return f"Round {self.round_number}: {self.action_type} by {self.draft_team}"


class HeroDraftEvent(models.Model):
    """Audit log for hero draft events."""

    EVENT_CHOICES = [
        ("captain_connected", "Captain Connected"),
        ("captain_disconnected", "Captain Disconnected"),
        ("captain_ready", "Captain Ready"),
        ("draft_paused", "Draft Paused"),
        ("draft_resumed", "Draft Resumed"),
        ("roll_triggered", "Roll Triggered"),
        ("roll_result", "Roll Result"),
        ("choice_made", "Choice Made"),
        ("round_started", "Round Started"),
        ("hero_selected", "Hero Selected"),
        ("round_timeout", "Round Timeout"),
        ("draft_completed", "Draft Completed"),
    ]

    draft = models.ForeignKey(
        HeroDraft, on_delete=models.CASCADE, related_name="events"
    )
    event_type = models.CharField(max_length=32, choices=EVENT_CHOICES)
    draft_team = models.ForeignKey(
        DraftTeam,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="events",
    )
    metadata = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at"]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        invalidate_model(HeroDraftEvent)

    def __str__(self):
        return f"{self.event_type} at {self.created_at}"


class LeagueRating(models.Model):
    """Per-player rating within a specific league."""

    league = models.ForeignKey(
        League,
        on_delete=models.CASCADE,
        related_name="ratings",
    )
    player = models.ForeignKey(
        "CustomUser",
        on_delete=models.CASCADE,
        related_name="league_ratings",
    )

    # Base MMR at time of joining league
    base_mmr = models.IntegerField(
        default=0,
        help_text="Player's MMR when joining the league",
    )

    # Separate positive and negative stats for flexibility
    positive_stats = models.FloatField(
        default=0.0,
        help_text="Accumulated positive rating changes (wins)",
    )
    negative_stats = models.FloatField(
        default=0.0,
        help_text="Accumulated negative rating changes (losses)",
    )

    # Glicko-2 support (for future use)
    rating_deviation = models.FloatField(
        default=350.0,
        help_text="Rating deviation (uncertainty) for Glicko-2",
    )
    volatility = models.FloatField(
        default=0.06,
        help_text="Volatility for Glicko-2",
    )

    # Tracking
    games_played = models.PositiveIntegerField(default=0)
    wins = models.PositiveIntegerField(default=0)
    losses = models.PositiveIntegerField(default=0)
    last_played = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = ["league", "player"]
        ordering = ["-positive_stats", "negative_stats"]
        verbose_name = "League Rating"
        verbose_name_plural = "League Ratings"

    @property
    def total_elo(self):
        """Calculate total Elo as base_mmr + positive_stats - negative_stats."""
        return self.base_mmr + self.positive_stats - self.negative_stats

    @property
    def net_change(self):
        """Net rating change since joining the league."""
        return self.positive_stats - self.negative_stats

    def __str__(self):
        return f"{self.player.username} in {self.league.name}: {self.total_elo:.0f}"


class LeagueMatch(models.Model):
    """A recorded match within a league for rating purposes."""

    league = models.ForeignKey(
        League,
        on_delete=models.CASCADE,
        related_name="matches",
    )
    game = models.OneToOneField(
        "Game",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="league_match",
        help_text="Link to Game model if applicable",
    )

    # Match metadata
    played_at = models.DateTimeField(
        help_text="When the match was played",
    )
    stage = models.CharField(
        max_length=64,
        blank=True,
        default="",
        help_text="Tournament stage (e.g., 'quarterfinal', 'grand_final')",
    )
    bracket_slot = models.CharField(
        max_length=32,
        blank=True,
        null=True,
        help_text="Bracket position identifier",
    )

    # Finalization tracking
    is_finalized = models.BooleanField(
        default=False,
        help_text="Whether ratings have been calculated",
    )
    finalized_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When ratings were calculated",
    )

    # Recalculation tracking
    recalculation_count = models.PositiveIntegerField(
        default=0,
        help_text="Number of times this match has been recalculated",
    )
    last_recalculated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When ratings were last recalculated",
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-played_at"]
        verbose_name = "League Match"
        verbose_name_plural = "League Matches"

    def __str__(self):
        status = "finalized" if self.is_finalized else "pending"
        return f"Match {self.pk} in {self.league.name} ({status})"


class LeagueMatchParticipant(models.Model):
    """A player's participation in a league match."""

    TEAM_SIDE_CHOICES = [
        ("radiant", "Radiant"),
        ("dire", "Dire"),
    ]

    match = models.ForeignKey(
        LeagueMatch,
        on_delete=models.CASCADE,
        related_name="participants",
    )
    player = models.ForeignKey(
        "CustomUser",
        on_delete=models.CASCADE,
        related_name="league_match_participations",
    )
    player_rating = models.ForeignKey(
        LeagueRating,
        on_delete=models.CASCADE,
        related_name="match_participations",
    )

    # Team info
    team_side = models.CharField(
        max_length=8,
        choices=TEAM_SIDE_CHOICES,
    )

    # Snapshot at match time
    mmr_at_match = models.IntegerField(
        help_text="Player's base MMR at time of match",
    )
    elo_before = models.FloatField(
        help_text="Player's total Elo before this match",
    )
    elo_after = models.FloatField(
        help_text="Player's total Elo after this match",
    )

    # Rating calculation factors
    k_factor_used = models.FloatField(
        help_text="K-factor used in calculation",
    )
    rating_deviation_used = models.FloatField(
        default=350.0,
        help_text="Rating deviation at time of calculation",
    )
    age_decay_factor = models.FloatField(
        default=1.0,
        help_text="Age decay factor applied (1.0 = no decay)",
    )

    # Result
    is_winner = models.BooleanField()
    delta = models.FloatField(
        help_text="Rating change from this match",
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["match", "player"]
        ordering = ["team_side", "player__username"]
        verbose_name = "League Match Participant"
        verbose_name_plural = "League Match Participants"

    def __str__(self):
        result = "W" if self.is_winner else "L"
        return f"{self.player.username} ({result}) in Match {self.match_id}"
