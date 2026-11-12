"""In-game lobbies DraftForge asked dota_lobby for, and the events it sent back.

One GameLobby row per dota_lobby lobby, so a game keeps its lobby history; at
most one row per game has not ended. The lobby password is never stored: see
lobby.passwords.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from lobby import passwords, states


class GameLobby(models.Model):
    class State(models.TextChoices):
        REQUESTED = states.REQUESTED, "Requested"
        ERROR = states.ERROR, "Error"
        PENDING = states.PENDING, "Pending"
        CREATING = states.CREATING, "Creating"
        WAITING = states.WAITING, "Waiting for players"
        READY = states.READY, "Ready"
        LAUNCHING = states.LAUNCHING, "Launching"
        IN_GAME = states.IN_GAME, "In game"
        POST_GAME = states.POST_GAME, "Post game"
        FINISHED = states.FINISHED, "Finished"
        FAILED = states.FAILED, "Failed"
        CLOSING = states.CLOSING, "Closing"
        CLOSED = states.CLOSED, "Closed"
        TIMED_OUT = states.TIMED_OUT, "Timed out"

    class Trigger(models.TextChoices):
        AUTO = "auto", "Automatic"
        MANUAL = "manual", "Manual"

    game = models.ForeignKey(
        "app.Game", related_name="lobbies", on_delete=models.CASCADE
    )
    external_ref = models.CharField(max_length=128, db_index=True)
    # dota_lobby's ID (lob_...), null until the create request is accepted.
    lobby_id = models.CharField(max_length=40, unique=True, null=True, blank=True)
    state = models.CharField(
        max_length=16, choices=State.choices, default=State.REQUESTED
    )
    state_reason = models.CharField(max_length=64, blank=True, default="")
    # Kept in step with `state` by save(); the partial unique constraint
    # below needs a plain column.
    ended = models.BooleanField(default=False, db_index=True)
    trigger = models.CharField(
        max_length=8, choices=Trigger.choices, default=Trigger.MANUAL
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        related_name="+",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    # Fingerprint of the secret key the lobby password is derived with, so
    # rotating DJANGO_SECRET_KEY keeps existing passwords (lobby.passwords).
    password_key_id = models.CharField(max_length=16, blank=True, default="")
    # The create body exactly as sent, without the password, so a retry
    # rebuilds a byte-identical request and dota_lobby answers 200, not 409.
    request = models.JSONField(default=dict, blank=True)

    # The teams actually sent as Radiant and Dire. Game.radiant_team and
    # Game.dire_team are bracket slots, not in-game sides.
    radiant_team = models.ForeignKey(
        "app.Team",
        related_name="+",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    dire_team = models.ForeignKey(
        "app.Team",
        related_name="+",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    bot = models.CharField(max_length=64, blank=True, default="")
    # 64-bit game coordinator ID, kept as dota_lobby sends it (a string).
    gc_lobby_id = models.CharField(max_length=24, blank=True, default="")
    league_id = models.IntegerField(null=True, blank=True)
    league_verified = models.BooleanField(null=True, blank=True)

    # Highest event seq applied; events arrive in order per lobby.
    last_seq = models.PositiveIntegerField(default=0)
    # {account_id: {status, seat, ready, invites_sent, last_invite_at}}
    players = models.JSONField(default=dict, blank=True)
    pending_invites = models.JSONField(default=list, blank=True)
    launch_attempts = models.PositiveSmallIntegerField(default=0)

    # Match data reported by the lobby. The result is provisional: staff
    # confirm it, and the Steam league sync stays authoritative.
    match_id = models.BigIntegerField(null=True, blank=True)
    provisional_outcome = models.SmallIntegerField(null=True, blank=True)
    provisional_outcome_name = models.CharField(max_length=32, blank=True, default="")
    provisional_winner_side = models.CharField(max_length=8, blank=True, default="")
    provisional_winner_team = models.ForeignKey(
        "app.Team",
        related_name="+",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    provisional_scored = models.BooleanField(null=True, blank=True)
    duration_seconds = models.IntegerField(null=True, blank=True)
    match_started_at = models.DateTimeField(null=True, blank=True)
    match_ended_at = models.DateTimeField(null=True, blank=True)

    # The last dota_lobby problem `code` (or a client code such as
    # "unreachable"), shown to organizers.
    last_error_code = models.CharField(max_length=48, blank=True, default="")
    last_error_detail = models.TextField(blank=True, default="")
    last_error_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    accepted_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    last_synced_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["game"],
                condition=Q(ended=False),
                name="lobby_one_active_per_game",
            ),
        ]
        indexes = [
            models.Index(fields=["ended", "state"], name="lobby_ended_state_idx"),
        ]
        ordering = ["-created_at", "-pk"]

    def __str__(self) -> str:
        return f"{self.external_ref} ({self.lobby_id or 'unaccepted'}, {self.state})"

    def save(self, *args: object, **kwargs: object) -> None:
        self.ended = self.state in states.ENDED_STATES
        if self.ended and self.ended_at is None:
            self.ended_at = timezone.now()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "state" in update_fields:
            update_fields = {*update_fields, "ended", "ended_at"}
        if not self.password_key_id:
            self.password_key_id = self._pick_password_key_id()
            if update_fields is not None:
                update_fields = {*update_fields, "password_key_id"}
        if update_fields is not None:
            kwargs["update_fields"] = update_fields
        super().save(*args, **kwargs)

    def _pick_password_key_id(self) -> str:
        """The key of this game's previous lobby while it is still configured.

        A recreated lobby then sends the same password as the one it replaces,
        so a create that dota_lobby did accept is replayed, not refused.
        """
        previous = (
            GameLobby.objects.filter(external_ref=self.external_ref)
            .exclude(pk=self.pk)
            .exclude(password_key_id="")
            .order_by("-created_at", "-pk")
            .values_list("password_key_id", flat=True)
            .first()
        )
        if previous and passwords.is_key_available(previous):
            return previous
        return passwords.current_key_id()


class GameLobbyEvent(models.Model):
    """One dota_lobby event, stored once by its ID (deliveries repeat)."""

    class Source(models.TextChoices):
        WEBHOOK = "webhook", "Webhook"
        POLL = "poll", "Poll"

    event_id = models.CharField(max_length=40, primary_key=True)
    lobby = models.ForeignKey(
        GameLobby, related_name="events", on_delete=models.CASCADE
    )
    seq = models.PositiveIntegerField()
    type = models.CharField(max_length=40)
    occurred_at = models.DateTimeField()
    # The whole envelope as received.
    payload = models.JSONField()
    source = models.CharField(max_length=8, choices=Source.choices)
    received_at = models.DateTimeField(default=timezone.now)
    applied_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["lobby", "seq"], name="lobby_event_unique_seq"
            ),
        ]
        ordering = ["lobby", "seq"]

    def __str__(self) -> str:
        return f"{self.event_id} #{self.seq} {self.type}"
