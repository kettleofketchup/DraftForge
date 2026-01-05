import logging

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


# Enum for Dota2 positions
class PositionEnum(IntEnum):
    Carry = 1
    Mid = 2
    Offlane = 3
    SoftSupport = 4
    HardSupport = 5


# Enum for Dota2 positions
class DraftStyles(StrEnum):
    snake = ("snake",)
    normal = ("normal",)


class CustomUser(AbstractUser):
    steamid = models.IntegerField(null=True, unique=True, blank=True)
    nickname = models.TextField(null=True, blank=True)
    mmr = models.IntegerField(null=True, blank=True)
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
        if the user doesn't have one.
        """
        if not self.positions_id:  # Check if positions is not set
            # Create a default PositionsModel with all positions set to 0
            default_positions = PositionsModel.objects.create()
            self.positions = default_positions

        super().save(*args, **kwargs)

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
    date_played = models.DateField()
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

    def __str__(self):
        return self.name

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
    members = models.ManyToManyField(
        User, related_name="teams_as_member", blank=True, null=True
    )
    dropin_members = models.ManyToManyField(
        User, related_name="teams_as_dropin", blank=True, null=True
    )
    left_members = models.ManyToManyField(
        User, related_name="teams_as_left", blank=True, null=True
    )

    current_points = models.IntegerField(default=0, blank=True)

    def __str__(self):
        return self.name

    @property
    def games(self):
        return Game.objects.filter(
            models.Q(radiant_team=self) | models.Q(dire_team=self)
        )


class GameStat(models.Model):
    user = models.ForeignKey(
        User, related_name="games", on_delete=models.CASCADE, blank=True
    )
    game = models.ForeignKey(
        "Game", related_name="stats", on_delete=models.CASCADE, blank=True
    )
    team = models.ForeignKey("Team", on_delete=models.CASCADE, blank=True)
    kills = models.IntegerField(default=0, blank=True)
    deaths = models.IntegerField(default=0, blank=True)
    assists = models.IntegerField(default=0, blank=True)
    hero_damage = models.IntegerField(default=0, blank=True)
    tower_damage = models.IntegerField(default=0, blank=True)
    gold_per_minute = models.IntegerField(default=0, blank=True)
    xp_per_minute = models.IntegerField(default=0, blank=True)
    radiant = models.BooleanField(blank=True, default=False)

    def __str__(self):
        return f"{self.user.username} stats for {self.game}"

    @property
    def team(self):
        if not self.game:
            return
        if not self.user:
            return


class Game(models.Model):
    tournament = models.ForeignKey(
        Tournament, related_name="games", on_delete=models.CASCADE, blank=True
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

    # Elimination type - determines what happens to loser
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

    # Match flow for losers (when elimination_type='double')
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
        return f"{self.radiant_team.name} vs {self.dire_team.name} in {self.tournament.name}"

    @property
    def teams(self):
        return [self.radiant_team, self.dire_team]


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
    ]

    draft_style = models.CharField(
        max_length=10,
        choices=DRAFT_STYLE_CHOICES,
        default="snake",
        help_text="Draft style: snake or normal",
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


class DraftRound(models.Model):
    draft = models.ForeignKey(
        Draft,
        related_name="draft_rounds",
        on_delete=models.CASCADE,
    )
    captain = models.ForeignKey(
        User, related_name="draft_rounds_captained", on_delete=models.CASCADE
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

        log.debug(
            f"Draft round {self.pk} picking player {user.username} for captain {self.captain.username}"
        )
        log.debug(self.draft.users_remaining)

        # Debug the current state
        remaining_count_before = self.draft.users_remaining.count()
        log.debug(f"Users remaining before pick: {remaining_count_before}")

        if self.draft.users_remaining.filter(id=user.id).exists():
            self.choice = user
            self.team.members.add(user)
            self.team.save()
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
