import uuid

from django.db import models

from app.models import CustomUser
from draft.models.hero import HeroDraft


class HeroDraftChatMessage(models.Model):
    """Team or all-chat message in a hero draft. Not cached; never invalidates the draft."""

    class Channel(models.TextChoices):
        TEAM = "team", "Team"
        ALL = "all", "All"

    class Kind(models.TextChoices):
        TEXT = "text", "Text"
        SUGGEST_PICK = "suggest_pick", "Suggest pick"
        SUGGEST_BAN = "suggest_ban", "Suggest ban"

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    draft = models.ForeignKey(
        HeroDraft, on_delete=models.CASCADE, related_name="chat_messages"
    )
    channel = models.CharField(max_length=8, choices=Channel.choices)
    team = models.ForeignKey(
        "app.Team",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )
    sender = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="+")
    kind = models.CharField(max_length=16, choices=Kind.choices, default=Kind.TEXT)
    hero_id = models.PositiveSmallIntegerField(null=True, blank=True)
    body = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["id"]
        indexes = [models.Index(fields=["draft", "channel", "team", "-id"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(channel="all", team__isnull=True)
                | models.Q(channel="team", team__isnull=False),
                name="herodraft_chat_channel_team",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(kind="text", hero_id__isnull=True) & ~models.Q(body="")
                )
                | models.Q(
                    kind__in=["suggest_pick", "suggest_ban"],
                    hero_id__isnull=False,
                    channel="team",
                ),
                name="herodraft_chat_kind_shape",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.channel} {self.kind} in draft {self.draft_id}"


class HeroDraftChatMembership(models.Model):
    """One continuous stint of a user on a team, as seen by this draft's chat."""

    draft = models.ForeignKey(HeroDraft, on_delete=models.CASCADE, related_name="+")
    team = models.ForeignKey("app.Team", on_delete=models.CASCADE, related_name="+")
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="+")
    joined_at = models.DateTimeField()
    left_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [models.Index(fields=["draft", "user", "left_at"])]
        constraints = [
            models.UniqueConstraint(
                fields=["draft", "user"],
                condition=models.Q(left_at__isnull=True),
                name="one_open_chat_membership_per_draft_user",
            )
        ]

    def __str__(self) -> str:
        return f"user {self.user_id} on team {self.team_id} in draft {self.draft_id}"
