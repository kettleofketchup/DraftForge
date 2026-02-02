from django.db import models


class LeagueUser(models.Model):
    """User's membership in a league with MMR snapshot from their org membership."""

    user = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.CASCADE,
        related_name="league_memberships",
        db_index=True,
    )
    org_user = models.ForeignKey(
        "org.OrgUser",
        on_delete=models.CASCADE,
        related_name="league_memberships",
        db_index=True,
    )
    league = models.ForeignKey(
        "app.League",
        on_delete=models.CASCADE,
        related_name="members",
    )
    mmr = models.IntegerField(default=0, db_index=True)
    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ["user", "league"]

    def __str__(self):
        return f"{self.user.username} in {self.league.name}"
