from django.conf import settings
from django.db import models
from django.utils import timezone
from social_django.models import USER_MODEL  # fix: skip
from social_django.models import AbstractUserSocialAuth, DjangoStorage

User = settings.AUTH_USER_MODEL
from django.contrib.auth.models import AbstractUser


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
    steamid = models.IntegerField(null=True)
    nickname = models.TextField(null=True)
    mmr = models.IntegerField(null=True)
    position = models.TextField(null=True)
    avatar = models.TextField(null=True)
    discordId = models.TextField(null=True)
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

    name = models.CharField(max_length=255)
    date_played = models.DateField()
    users = models.ManyToManyField(User, related_name="tournaments")
    teams = models.ManyToManyField("Team", related_name="tournaments")
    winning_team = models.ForeignKey(
        "Team",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="tournaments_won",
    )
    state = models.CharField(max_length=20, choices=STATE_CHOICES, default="future")

    def __str__(self):
        return self.name


class Team(models.Model):
    name = models.CharField(max_length=255)
    captain = models.ForeignKey(
        User, related_name="teams_captained", on_delete=models.CASCADE
    )
    members = models.ManyToManyField(User, related_name="teams_member", blank=True)
    dropin_members = models.ManyToManyField(
        User, related_name="teams_dropin", blank=True
    )
    current_points = models.IntegerField(default=0)

    def __str__(self):
        return self.name


class Game(models.Model):
    tournament = models.ForeignKey(
        Tournament, related_name="games", on_delete=models.CASCADE
    )
    team1 = models.ForeignKey(
        Team, related_name="matches_as_team1", on_delete=models.CASCADE
    )
    team2 = models.ForeignKey(
        Team, related_name="matches_as_team2", on_delete=models.CASCADE
    )
    winning_team = models.ForeignKey(
        Team, related_name="games_won", on_delete=models.CASCADE
    )

    def __str__(self):
        return f"{self.team1.name} vs {self.team2.name} in {self.tournament.name}"

    @property
    def teams(self):
        return [self.team1, self.team2]
