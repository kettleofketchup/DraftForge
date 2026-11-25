import uuid

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Additive: external receipts and the per-DM outbox.

    No backfill. Sends recorded before this migration get no outbox row.
    """

    dependencies = [
        ("events", "0040_retarget_tournament_to_tournament"),
        ("org", "0026_api_token_operations"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ExternalPromotionReceipt",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("source", models.CharField(choices=[("contact_log", "Contact log")], max_length=16)),
                ("source_contact_id", models.BigIntegerField()),
                ("discord_id", models.CharField(max_length=20)),
                ("recorded_at", models.DateTimeField()),
                (
                    "contact_method",
                    models.CharField(
                        choices=[
                            ("DISCORD_DM", "Discord DM"),
                            ("DISCORD_GROUP_DM", "Discord group DM"),
                            ("OTHER", "Other"),
                        ],
                        max_length=24,
                    ),
                ),
                (
                    "linkage",
                    models.CharField(
                        choices=[
                            ("occasion", "Occasion"),
                            ("event_date", "Event date"),
                        ],
                        max_length=16,
                    ),
                ),
                ("source_hash", models.CharField(max_length=64)),
                (
                    "first_imported_at",
                    models.DateTimeField(default=django.utils.timezone.now),
                ),
                (
                    "association_state",
                    models.CharField(
                        choices=[
                            ("unresolved", "Unresolved"),
                            ("linked", "Linked"),
                            ("quarantined", "Quarantined"),
                        ],
                        default="unresolved",
                        max_length=16,
                    ),
                ),
                (
                    "association_reason",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("", "None"),
                            (
                                "discord_owner_changed",
                                "Discord ID owned by another account",
                            ),
                            ("org_user_mismatch", "Membership of another account"),
                            ("account_deleted", "Account deleted"),
                        ],
                        default="",
                        max_length=32,
                    ),
                ),
                ("association_updated_at", models.DateTimeField(blank=True, null=True)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="external_promotion_receipts",
                        to="events.event",
                    ),
                ),
                (
                    "org_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="external_promotion_receipts",
                        to="org.orguser",
                    ),
                ),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="external_promotion_receipts",
                        to="org.organization",
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="external_promotion_receipts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["event", "discord_id"],
                        name="ext_promo_rcpt_event_discord",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("organization", "source", "source_contact_id"),
                        name="uniq_external_promo_receipt_source_id",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="PromotionContactOutbox",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("local_send_id", models.BigIntegerField()),
                ("event_id", models.BigIntegerField(db_index=True)),
                (
                    "sender_user_id",
                    models.BigIntegerField(blank=True, db_index=True, null=True),
                ),
                (
                    "recipient_user_id",
                    models.BigIntegerField(blank=True, db_index=True, null=True),
                ),
                ("sent_at", models.DateTimeField()),
                (
                    "delivery_id",
                    models.UUIDField(default=uuid.uuid4, editable=False, unique=True),
                ),
                ("payload", models.JSONField(blank=True, null=True)),
                (
                    "payload_hash",
                    models.CharField(blank=True, default="", max_length=64),
                ),
                (
                    "state",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("in_flight", "In flight"),
                            ("retry", "Retry"),
                            ("paused", "Paused"),
                            ("reconciliation_required", "Reconciliation required"),
                            ("applied", "Applied"),
                            ("canceled", "Canceled"),
                        ],
                        default="pending",
                        max_length=24,
                    ),
                ),
                ("attempts", models.PositiveIntegerField(default=0)),
                ("due_at", models.DateTimeField(blank=True, null=True)),
                ("lease_token", models.UUIDField(blank=True, null=True)),
                ("lease_expires_at", models.DateTimeField(blank=True, null=True)),
                (
                    "last_reason",
                    models.CharField(blank=True, default="", max_length=64),
                ),
                (
                    "applied_contact_log_id",
                    models.BigIntegerField(blank=True, null=True),
                ),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "organization",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="promotion_contact_outbox",
                        to="org.organization",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(
                        fields=["state", "due_at"], name="promo_outbox_state_due"
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("organization", "local_send_id"),
                        name="uniq_promo_outbox_local_send",
                    )
                ],
            },
        ),
    ]
