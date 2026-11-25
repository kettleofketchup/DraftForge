from uuid import uuid4

from django.db import models
from django.db.models import Q
from django.utils import timezone

from org.mmr_requests.storage import private_media_storage

SCREENSHOT_EXTENSIONS = frozenset({"png", "jpeg", "webp"})
TEXT_MAX_LENGTH = 500


def mmr_screenshot_path(instance: "MmrChangeRequest", filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower()
    if ext not in SCREENSHOT_EXTENSIONS:
        raise ValueError(f"Unsupported screenshot extension: {ext!r}")
    now = timezone.now()
    return f"mmr_requests/{now:%Y}/{now:%m}/{uuid4().hex}.{ext}"


class MmrChangeRequest(models.Model):
    """A member's request (or a staff-set record) to change an org or league MMR."""

    class Target(models.TextChoices):
        ORG = "org", "Org"
        LEAGUE = "league", "League"

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"
        SUPERSEDED = "superseded", "Superseded"

    class Source(models.TextChoices):
        MEMBER = "member", "Member"
        STAFF = "staff", "Staff"

    requester = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.CASCADE,
        related_name="mmr_requests_made",
    )
    subject_user = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.CASCADE,
        related_name="mmr_requests_about",
    )
    organization = models.ForeignKey(
        "org.Organization",
        on_delete=models.CASCADE,
        related_name="mmr_requests",
    )
    org_user = models.ForeignKey(
        "org.OrgUser",
        on_delete=models.SET_NULL,
        null=True,
        related_name="mmr_requests",
    )
    league = models.ForeignKey(
        "league.League",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="mmr_requests",
    )
    league_user = models.ForeignKey(
        "league.LeagueUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mmr_requests",
    )
    target = models.CharField(max_length=10, choices=Target.choices)
    game_type = models.PositiveSmallIntegerField()
    requested_mmr = models.PositiveIntegerField()
    approved_mmr = models.PositiveIntegerField(null=True, blank=True)
    previous_mmr = models.PositiveIntegerField()
    previous_verified = models.BooleanField(default=False)
    screenshot = models.FileField(
        upload_to=mmr_screenshot_path,
        storage=private_media_storage,
        max_length=255,
        blank=True,
    )
    screenshot_content_type = models.CharField(max_length=32, blank=True)
    note = models.TextField(blank=True, max_length=TEXT_MAX_LENGTH)
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True,
    )
    source = models.CharField(
        max_length=8, choices=Source.choices, default=Source.MEMBER
    )
    reviewed_by = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="mmr_requests_reviewed",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, max_length=TEXT_MAX_LENGTH)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["organization", "status", "-created_at"],
                name="mmrreq_org_status_idx",
            ),
            models.Index(
                fields=["league", "status", "-created_at"],
                name="mmrreq_league_status_idx",
            ),
            models.Index(
                fields=["subject_user", "status"], name="mmrreq_subject_status_idx"
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["org_user", "game_type"],
                condition=Q(status="pending", target="org"),
                name="unique_pending_org_mmr_request",
            ),
            models.UniqueConstraint(
                fields=["league_user"],
                condition=Q(status="pending", target="league"),
                name="unique_pending_league_mmr_request",
            ),
            models.CheckConstraint(
                condition=Q(target="org", league__isnull=True, league_user__isnull=True)
                | Q(target="league", league__isnull=False),
                name="mmr_request_target_shape",
            ),
            models.CheckConstraint(
                condition=~Q(status="pending")
                | (
                    Q(org_user__isnull=False)
                    & (Q(target="org") | Q(league_user__isnull=False))
                ),
                name="mmr_request_pending_has_membership",
            ),
            models.CheckConstraint(
                condition=Q(source="staff") | Q(status="cancelled") | ~Q(screenshot=""),
                name="mmr_request_member_screenshot_required",
            ),
        ]

    def __str__(self) -> str:
        return f"MmrChangeRequest#{self.pk} {self.target} {self.status}"
