from django.db import models
from django.utils import timezone


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
    RANK_STATUSES = tuple(value for value, _ in RANK_STATUS_CHOICES)
    DEFAULT_RANK_STATUS = "never"
    # Same rule as the org 0011 backfill (org/tests/rank_evidence_cases.py).
    RANK_EVIDENCE_FIELDS = (
        "rank_medal",
        "battle_cup_tier",
        "rank_screenshot",
        "battlecup_screenshot",
    )

    org_user = models.OneToOneField(
        "org.OrgUser",
        on_delete=models.CASCADE,
        related_name="dota_profile",
    )
    rank_status = models.CharField(
        max_length=10, choices=RANK_STATUS_CHOICES, default=DEFAULT_RANK_STATUS
    )
    rank_declared_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the player last chose a rank status; null means undeclared",
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

    def declare_rank(self, rank_status: str) -> None:
        """Record an explicit rank answer; the caller saves."""
        if rank_status not in self.RANK_STATUSES:
            raise ValueError(f"Unknown rank status: {rank_status!r}")
        self.rank_status = rank_status
        self.rank_declared_at = timezone.now()

    @property
    def is_rank_declared(self) -> bool:
        return (
            self.rank_declared_at is not None and self.rank_status in self.RANK_STATUSES
        )

    def has_rank_evidence(self) -> bool:
        """True when the row departs from the default rank answer."""
        return self.rank_status != self.DEFAULT_RANK_STATUS or any(
            getattr(self, field) not in ("", None)
            for field in self.RANK_EVIDENCE_FIELDS
        )

    def sync_rank_declaration(self, previous_status: str) -> None:
        """Declare after an edit that changed the status or added rank evidence.

        Re-sending the stored status alone (as the profile card does) is not a
        declaration; the caller saves.
        """
        if self.rank_status != previous_status or (
            self.rank_declared_at is None and self.has_rank_evidence()
        ):
            self.declare_rank(self.rank_status)

    class Meta:
        verbose_name = "Player Dota Profile"

    def __str__(self) -> str:
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

    def __str__(self) -> str:
        return f"{self.org_user} — Deadlock ({self.rank or 'unranked'})"
