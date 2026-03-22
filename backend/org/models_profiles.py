from django.db import models


class PlayerProfileMixin(models.Model):
    """Abstract mixin for game-specific player profiles.

    Provides friend_id — the Dota 2 Friend ID (32-bit Steam account ID)
    entered via Discord modal. This is self-reported and unverified.
    Verification happens separately (Steam OAuth or admin approval).
    """

    unverified_friend_id = models.CharField(
        max_length=20,
        blank=True,
        default="",
        help_text="Dota 2 Friend ID (self-reported, unverified)",
    )

    class Meta:
        abstract = True


class PlayerDotaProfile(PlayerProfileMixin):
    """Dota 2-specific player profile, scoped to an org membership."""

    RANK_STATUS_CHOICES = [
        ("active", "Active"),
        ("previous", "Previously Ranked"),
        ("never", "Never Ranked"),
    ]

    org_user = models.OneToOneField(
        "org.OrgUser",
        on_delete=models.CASCADE,
        related_name="dota_profile",
    )
    rank_status = models.CharField(
        max_length=10, choices=RANK_STATUS_CHOICES, default="never"
    )
    rank_medal = models.CharField(
        max_length=50,
        blank=True,
        default="",
        help_text="Medal tier (Herald, Guardian, Crusader, Archon, Legend, Ancient, Divine, Immortal)",
    )
    rank_date = models.DateField(
        null=True,
        blank=True,
        help_text="When user last held this rank (for 'previous' status)",
    )
    battle_cup_tier = models.IntegerField(
        null=True,
        blank=True,
        help_text="Max battle cup ticket tier (for 'never' ranked users)",
    )
    mmr = models.IntegerField(
        null=True,
        blank=True,
        help_text="Self-reported numeric MMR",
    )
    rank_screenshot = models.URLField(
        max_length=500,
        blank=True,
        default="",
        help_text="URL to uploaded MMR screenshot",
    )
    battlecup_screenshot = models.URLField(
        max_length=500,
        blank=True,
        default="",
        help_text="URL to uploaded battle cup ticket screenshot",
    )
    pos_1 = models.BooleanField(default=False, help_text="Carry")
    pos_2 = models.BooleanField(default=False, help_text="Mid")
    pos_3 = models.BooleanField(default=False, help_text="Offlane")
    pos_4 = models.BooleanField(default=False, help_text="Soft Support")
    pos_5 = models.BooleanField(default=False, help_text="Hard Support")

    class Meta:
        verbose_name = "Player Dota Profile"

    def __str__(self):
        return f"{self.org_user} — Dota ({self.rank_status})"


class PlayerDeadlockProfile(PlayerProfileMixin):
    """Deadlock-specific player profile, scoped to an org membership."""

    org_user = models.OneToOneField(
        "org.OrgUser",
        on_delete=models.CASCADE,
        related_name="deadlock_profile",
    )
    rank = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Self-reported rank (loose string)",
    )
    rank_date = models.DateField(
        null=True,
        blank=True,
        help_text="When user last played ranked",
    )

    class Meta:
        verbose_name = "Player Deadlock Profile"

    def __str__(self):
        return f"{self.org_user} — Deadlock ({self.rank or 'unranked'})"
