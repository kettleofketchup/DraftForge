import logging

import requests
from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import models
from django.db.utils import IntegrityError
from django.utils import timezone
from social_django.models import USER_MODEL  # fix: skip
from social_django.models import AbstractUserSocialAuth, DjangoStorage

User = settings.AUTH_USER_MODEL

from enum import IntEnum

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


# Enum for Dota2 positions
class PositionEnum(IntEnum):
    Carry = 1
    Mid = 2
    Offlane = 3
    SoftSupport = 4
    HardSupport = 5


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

        try:
            headers = {
                "Authorization": f"Bot {settings.DISCORD_BOT_TOKEN}",
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
    winning_team = models.ForeignKey(
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


class Draft(models.Model):

    tournament = models.ForeignKey(
        Tournament,
        related_name="draft",
        on_delete=models.CASCADE,
        blank=True,
        null=True,
    )

    def __str__(self):
        return f"Draft {self.pk} in {self.tournament.name}"

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

        return (
            self.tournament.users.exclude(teams_as_member__tournament=self.tournament)
            .exclude(teams_as_dropin__tournament=self.tournament)
            .exclude(teams_as_left__tournament=self.tournament)
            .exclude(teams_as_captain__tournament=self.tournament)
            .distinct()
        )

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
        logging.debug(f"Building draft rounds")

        for round in self.draft_rounds.all():
            logging.debug(
                f"Draft round {round.pk} already exists for {self.tournament.name}"
            )
            round.delete()

        max_picks = self.tournament.captains.count() * 4 + 1

        pick = 1
        phase = 1
        order = self.tournament.teams.order_by("draft_order")

        def pick_player(draft, team, pick, phase):
            try:
                draftRound = DraftRound.objects.create(
                    draft=draft,
                    captain=team.captain,
                    pick_number=pick,
                    pick_phase=phase,
                )
                draftRound.save()

            except IntegrityError:
                logging.error(
                    f"IntegrityError: Draft round already exists for {team.name} in phase {phase}, pick {pick}"
                )
                pick += 1
                if pick % 5 == 0:
                    phase += 1
                return pick, phase

            logging.debug(
                f"Draft round {draftRound.pk} created for {team.name} in phase {phase}, pick {pick}"
            )
            pick += 1
            if pick % 5 == 0:
                phase += 1

            return pick, phase

        while pick < max_picks:
            for team in self.tournament.teams.order_by("draft_order").all():
                pick, phase = pick_player(self, team, pick, phase)
                logging.debug(f" phase {phase}, pick {pick}")
                if pick >= max_picks:
                    break
            for team in self.tournament.teams.order_by("draft_order").reverse():

                pick, phase = pick_player(self, team, pick, phase)
                logging.debug(f" phase {phase}, pick {pick}")

                if pick >= max_picks:
                    break
        for round in self.draft_rounds.all():
            logging.debug(f"Draft round {round.pk} created for {self.tournament.name}")
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
        log.debug(self.draft.users_remaining)
        if self.draft.users_remaining.contains(user):
            self.choice = user
            self.team.members.add(user)
            self.team.save()
            self.save()
        else:
            raise ValueError("User is not available for drafting.")

    def __str__(self):
        return f"{self.picker.username} picked {self.choice.username} in {self.tournament.name}"
