from django.core.validators import MaxLengthValidator
from django.db import models
from django.utils import timezone


class PromoTemplate(models.Model):
    """Reusable Discord DM body an org's promoters send to players."""

    organization = models.ForeignKey(
        "app.Organization",
        on_delete=models.CASCADE,
        related_name="promo_templates",
    )
    name = models.CharField(max_length=100)
    body = models.TextField(max_length=2000, validators=[MaxLengthValidator(2000)])
    created_by = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return f"{self.name} @ org {self.organization_id}"


class PromoSend(models.Model):
    """One promotion DM a promoter recorded sending for an event."""

    organization = models.ForeignKey(
        "app.Organization",
        on_delete=models.CASCADE,
        related_name="promo_sends",
    )
    event = models.ForeignKey(
        "events.Event",
        on_delete=models.CASCADE,
        related_name="promo_sends",
    )
    recipient = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="promo_received",
    )
    sender = models.ForeignKey(
        "app.CustomUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="promo_sent",
    )
    template = models.ForeignKey(
        "org.PromoTemplate",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sends",
    )
    text = models.TextField(max_length=4000, validators=[MaxLengthValidator(4000)])
    earns_points = models.BooleanField(default=False)
    sent_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["event", "recipient"],
                condition=models.Q(earns_points=True),
                name="uniq_earning_promo_send",
            ),
        ]
        indexes = [models.Index(fields=["event", "recipient"])]

    def __str__(self) -> str:
        return f"promo event {self.event_id} -> user {self.recipient_id}"
