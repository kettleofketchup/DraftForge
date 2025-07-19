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


class DotaInfo(models.Model):
    user = models.ForeignKey(USER_MODEL, name="dota", on_delete=models.CASCADE)
    steamid = models.IntegerField(null=True)
    mmr = models.IntegerField(null=True)
    position = models.TextField(null=True)


class DiscordInfo(models.Model):
    discordId = models.IntegerField(null=True)
    avatarId = models.IntegerField(null=True)
    avatarUrl = models.URLField(null=True)


class CustomUser(AbstractUser):
    steamid = models.IntegerField(null=True, unique=True)
    nickname = models.TextField(null=True)
    mmr = models.IntegerField(null=True)
    # Store positions as a dict of 1-5: bool, e.g. {"1": true, "2": false, ...}
    positions = JSONField(
        default=dict, help_text="Dota2 positions: 1-5 as keys, bool as value"
    )
    avatar = models.TextField(null=True)
    discordId = models.TextField(null=True, unique=True)
    discordUsername = models.TextField(null=True)
    discordNickname = models.TextField(null=True)
    guildNickname = models.TextField(null=True)

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
    teams = models.ManyToManyField("Team", related_name="tournament")
    winning_team = models.ForeignKey(
        "Team",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tournaments_won",
    )
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default="future")
    tournment_type = models.CharField(
        max_length=20, choices=TOURNAMNET_TYPE_CHOICES, default="double_elimination"
    )

    def __str__(self):
        return self.name


class Team(models.Model):
    name = models.CharField(max_length=255)
    captain = models.ForeignKey(
        User, related_name="teams_captained", on_delete=models.CASCADE
    )
    members = models.ManyToManyField(User, related_name="teams", blank=True)
    dropin_members = models.ManyToManyField(
        User, related_name="teams_dropin", blank=True
    )
    left_members = models.ManyToManyField(User, related_name="teams_leftzs", blank=True)

    current_points = models.IntegerField(default=0)

    def __str__(self):
        return self.name


class Game(models.Model):
    tournament = models.ForeignKey(
        Tournament, related_name="tournament_games", on_delete=models.CASCADE
    )
    round = models.IntegerField(default=1)
    radiant = models.ForeignKey(
        Team, related_name="gamesRadiant", on_delete=models.CASCADE
    )
    dire = models.ForeignKey(Team, related_name="gamesDire", on_delete=models.CASCADE)
    winning_team = models.ForeignKey(
        Team, related_name="games_won", on_delete=models.CASCADE
    )

    def __str__(self):
        return f"{self.team1.name} vs {self.team2.name} in {self.tournament.name}"

    @property
    def teams(self):
        return [self.team1, self.team2]

    users = models.ManyToManyField(User, related_name="game_stats")
