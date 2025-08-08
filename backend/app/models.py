import logging
from django.db.utils import IntegrityError
from django.conf import settings
from django.db import models
from django.utils import timezone
from social_django.models import USER_MODEL  # fix: skip
from social_django.models import AbstractUserSocialAuth, DjangoStorage

User = settings.AUTH_USER_MODEL

from enum import IntEnum

from django.contrib.auth.models import AbstractUser
from django.db.models import JSONField


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
    positions = JSONField(
        default=dict,
        help_text="Dota2 positions: 1-5 as keys, bool as value",
        blank=True,
        null=True,
    )
    avatar = models.TextField(null=True, blank=True)
    discordId = models.TextField(null=True, unique=True, blank=True)
    discordUsername = models.TextField(null=True, blank=True)
    discordNickname = models.TextField(null=True, blank=True)
    guildNickname = models.TextField(null=True, blank=True)

    @property
    def avatarUrl(self):
        return f"https://cdn.discordapp.com/avatars/" f"{self.discordId}/{self.avatar}"


class Tournament(models.Model):
    STATE_CHOICES = [
        ("future", "Future"),
        ("in_progress", "In Progress"),
        ("past", "Past"),
    ]
    TOURNAMNET_TYPE_CHOICES = [
        ("single_elimination", "Single Elimination"),
        ("double_elimination", "Double Elimination"),
        ("swiss", "Swiss Bracket"),
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
        on_delete=models.CASCADE,
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
        User, related_name="game_stats", on_delete=models.CASCADE, blank=True
    )
    game = models.ForeignKey(
        "Game", related_name="stats", on_delete=models.CASCADE, blank=True
    )
    kills = models.IntegerField(default=0, blank=True)
    deaths = models.IntegerField(default=0, blank=True)
    assists = models.IntegerField(default=0, blank=True)
    hero_damage = models.IntegerField(default=0, blank=True)
    tower_damage = models.IntegerField(default=0, blank=True)
    gold_per_minute = models.IntegerField(default=0, blank=True)
    xp_per_minute = models.IntegerField(default=0, blank=True)

    def __str__(self):
        return f"{self.user.username} stats for {self.game}"


class Game(models.Model):
    users = models.ManyToManyField(User, related_name="games", blank=True)

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

        max_picks = self.tournament.captains.count() * 5

        pick = 0
        phase = 0
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

    def __str__(self):
        return f"{self.picker.username} picked {self.choice.username} in {self.tournament.name}"
