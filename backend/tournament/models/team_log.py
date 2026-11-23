from django.db import models

from tournament.models.team import Team


class TeamLogVia(models.TextChoices):
    WEB = "web", "Web"
    DISCORD = "discord", "Discord"
    API = "api", "API"
    SYSTEM = "system", "System"


class TeamLogAction(models.TextChoices):
    SET_CAPTAIN = "set_captain", "Set Captain"
    SET_DEPUTY = "set_deputy", "Set Deputy"
    MARK_DROPOUT = "mark_dropout", "Mark Dropout"
    RESTORE_MEMBER = "restore_member", "Restore Member"
    ADD_STANDIN = "add_standin", "Add Stand-in"
    REMOVE_STANDIN = "remove_standin", "Remove Stand-in"
    SUB_IN = "sub_in", "Sub In"
    RENAME = "rename", "Rename"
    LEGACY_PATCH = "legacy_patch", "Legacy Patch"
    SYSTEM_SUCCESSION = "system_succession", "System Succession"
    EMPTY_TEAM_KEPT = "empty_team_kept", "Empty Team Kept"
    TEAM_DELETED = "team_deleted", "Team Deleted"
    MATERIALIZE = "materialize", "Materialize"


class TeamLog(models.Model):
    """Append-only audit of staff and system team roster changes."""

    team = models.ForeignKey(
        Team,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="logs",
    )
    event_team = models.ForeignKey(
        "events.EventTeam",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="team_logs",
    )
    team_snapshot_id = models.PositiveIntegerField(null=True, blank=True)
    tournament_id = models.PositiveIntegerField(null=True, blank=True)
    event_id = models.PositiveIntegerField(null=True, blank=True)
    organization_id = models.PositiveIntegerField(null=True, blank=True)
    occasion_at = models.DateTimeField(null=True, blank=True)
    team_name = models.CharField(max_length=255, blank=True)
    actor = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        related_name="team_actions_performed",
    )
    via = models.CharField(max_length=16, choices=TeamLogVia.choices)
    action = models.CharField(max_length=32, choices=TeamLogAction.choices)
    target_user = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="team_actions_received",
    )
    reason = models.TextField(blank=True)
    override_rules = models.JSONField(default=list, blank=True)
    details = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "app_teamlog"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["team_snapshot_id", "-created_at"]),
            models.Index(fields=["event_id", "-created_at"]),
            models.Index(fields=["tournament_id", "-created_at"]),
        ]
        verbose_name = "Team Log"
        verbose_name_plural = "Team Logs"

    def __str__(self) -> str:
        actor_name = self.actor.username if self.actor else "System"
        return f"{actor_name} {self.action} on {self.team_name}"
