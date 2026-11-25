import uuid

import django.db.models.deletion
import django.utils.timezone
from django.apps.registry import Apps
from django.conf import settings
from django.db import migrations, models
from django.db.backends.base.schema import BaseDatabaseSchemaEditor

ACTION_CHOICES = [
    ("add_admin", "Add Admin"),
    ("remove_admin", "Remove Admin"),
    ("add_staff", "Add Staff"),
    ("remove_staff", "Remove Staff"),
    ("add_member", "Add Member"),
    ("transfer_ownership", "Transfer Ownership"),
    ("create", "Create Organization"),
    ("update", "Update Organization"),
    ("delete", "Delete Organization"),
    ("approve_claim", "Approve Profile Claim"),
    ("reject_claim", "Reject Profile Claim"),
    ("set_mmr", "Set MMR"),
    ("enable_feature", "Enable Feature"),
    ("disable_feature", "Disable Feature"),
    ("add_promoter", "Add Promoter"),
    ("remove_promoter", "Remove Promoter"),
    ("set_point_value", "Set Point Value"),
    ("rescore", "Rescore Contributions"),
    ("award_points", "Award Points"),
    ("edit_award", "Edit Award"),
    ("delete_award", "Delete Award"),
    ("complete_event", "Complete Event"),
    ("reopen_event", "Reopen Event"),
    ("set_event_staff", "Set Event Staff"),
    ("delete_user_contributions", "Delete User Contributions"),
    ("set_attendance", "Set Attendance"),
    ("finalize_attendance", "Finalize Attendance"),
    ("void_attendance", "Void Attendance"),
    ("void_captain_review", "Void Captain Review"),
    ("unvoid_captain_review", "Unvoid Captain Review"),
    ("release_captain_reviews", "Release Captain Reviews"),
    ("update_leadership_settings", "Update Leadership Settings"),
    ("update_captain_traits", "Update Captain Traits"),
    ("delete_user_leadership", "Delete User Leadership"),
    ("create_api_token", "Create API Token"),
    ("revoke_api_token", "Revoke API Token"),
    ("set_api_limits", "Set API Limits"),
    ("void_promo_point", "Void Promotion Point"),
    ("restore_promo_point", "Restore Promotion Point"),
    ("update_external_contact", "Update External Contact"),
]
REVERSAL_KINDS = ["promo_restore", "promo_void"]
MAX_DISCORD_ID = 20


def backfill_recipient_discord_id(
    apps: Apps, schema_editor: BaseDatabaseSchemaEditor
) -> None:
    PromoSend = apps.get_model("org", "PromoSend")
    sends = PromoSend.objects.filter(recipient__isnull=False).select_related(
        "recipient"
    )
    batch = []
    for send in sends.iterator(chunk_size=500):
        discord_id = send.recipient.discordId or ""
        if not discord_id or len(discord_id) > MAX_DISCORD_ID:
            continue
        send.recipient_discord_id = discord_id
        batch.append(send)
        if len(batch) >= 500:
            PromoSend.objects.bulk_update(batch, ["recipient_discord_id"])
            batch = []
    if batch:
        PromoSend.objects.bulk_update(batch, ["recipient_discord_id"])


class Migration(migrations.Migration):
    """Additive: the external contact ledger, the per-DM outbox and the
    promotion-point ledger links.

    Sends recorded before this migration get no outbox row; their
    ``recipient_discord_id`` is backfilled from the recipient's current
    Discord ID (the best snapshot still available).
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
                (
                    "source",
                    models.CharField(
                        choices=[("contact_log", "Contact log")], max_length=16
                    ),
                ),
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
                ("contact_date_ny", models.DateField()),
                (
                    "contact_reason",
                    models.CharField(
                        choices=[
                            ("EVENT_INVITE", "Event invite"),
                            ("FOLLOW_UP", "Follow-up"),
                            ("GENERAL", "General"),
                        ],
                        max_length=16,
                    ),
                ),
                ("occasion_id", models.BigIntegerField(blank=True, null=True)),
                ("event_date", models.DateTimeField(blank=True, null=True)),
                ("forced", models.BooleanField(default=False)),
                (
                    "promoter_discord_id",
                    models.CharField(blank=True, default="", max_length=20),
                ),
                ("source_revision", models.PositiveIntegerField(default=0)),
                ("source_updated_at", models.DateTimeField(blank=True, null=True)),
                ("retracted_at", models.DateTimeField(blank=True, null=True)),
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
                    "point_status",
                    models.CharField(
                        choices=[
                            ("not_applicable", "Not applicable"),
                            ("echo", "Echo of a local send"),
                            ("credited", "Credited"),
                            ("uncredited", "Uncredited"),
                            ("duplicate", "Duplicate"),
                            ("retracted", "Retracted"),
                        ],
                        default="not_applicable",
                        max_length=16,
                    ),
                ),
                (
                    "point_reason",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("", "None"),
                            ("promoter_unresolved", "Promoter unresolved"),
                            ("promoter_unmatched", "Promoter unmatched"),
                            ("promoter_not_member", "Promoter not a member"),
                            ("self_contact", "Self contact"),
                        ],
                        default="",
                        max_length=24,
                    ),
                ),
                ("holds_point", models.BooleanField(default=False)),
                ("origin_send_id", models.BigIntegerField(blank=True, null=True)),
                (
                    "event",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
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
                    ),
                    models.Index(
                        fields=["organization", "discord_id", "recorded_at"],
                        name="ext_promo_rcpt_org_discord_at",
                    ),
                    models.Index(
                        fields=["organization", "contact_date_ny"],
                        name="ext_promo_rcpt_org_date",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("organization", "source", "source_contact_id"),
                        name="uniq_external_promo_receipt_source_id",
                    ),
                    models.UniqueConstraint(
                        condition=models.Q(("holds_point", True)),
                        fields=("organization", "event", "discord_id"),
                        name="uniq_external_promo_point",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                ("event_date__isnull", True),
                                ("occasion_id__isnull", False),
                            ),
                            models.Q(
                                ("event_date__isnull", False),
                                ("occasion_id__isnull", True),
                            ),
                            _connector="OR",
                        ),
                        name="ck_ext_promo_rcpt_occasion_xor_date",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("forced", False),
                            ("occasion_id__isnull", False),
                            _connector="OR",
                        ),
                        name="ck_ext_promo_rcpt_forced_occasion",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("holds_point", False),
                            ("event__isnull", False),
                            _connector="OR",
                        ),
                        name="ck_ext_promo_rcpt_point_has_event",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                ("holds_point", True),
                                ("point_status__in", ["credited", "uncredited"]),
                            ),
                            models.Q(
                                ("holds_point", False),
                                models.Q(
                                    ("point_status__in", ["credited", "uncredited"]),
                                    _negated=True,
                                ),
                            ),
                            _connector="OR",
                        ),
                        name="ck_ext_promo_rcpt_point_status",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            models.Q(
                                ("retracted_at__isnull", True),
                                models.Q(("point_status", "retracted"), _negated=True),
                            ),
                            models.Q(
                                ("point_status", "retracted"),
                                ("retracted_at__isnull", False),
                            ),
                            _connector="OR",
                        ),
                        name="ck_ext_promo_rcpt_retracted",
                    ),
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
        migrations.AddField(
            model_name="contributionentry",
            name="external_contact",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="ledger_entries",
                to="org.externalpromotionreceipt",
            ),
        ),
        migrations.AddField(
            model_name="contributionentry",
            name="reversal_of",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="reversals",
                to="org.contributionentry",
            ),
        ),
        migrations.AddField(
            model_name="contributionentry",
            name="voided",
            field=models.BooleanField(default=False),
        ),
        migrations.AddConstraint(
            model_name="contributionentry",
            constraint=models.UniqueConstraint(
                condition=models.Q(
                    ("kind", "promo_message"),
                    ("external_contact__isnull", False),
                    ("voided", False),
                ),
                fields=("external_contact",),
                name="uniq_external_promo_credit",
            ),
        ),
        migrations.AddConstraint(
            model_name="contributionentry",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    models.Q(
                        ("kind__in", REVERSAL_KINDS), ("reversal_of__isnull", False)
                    ),
                    models.Q(
                        models.Q(("kind__in", REVERSAL_KINDS), _negated=True),
                        ("reversal_of__isnull", True),
                    ),
                    _connector="OR",
                ),
                name="ck_promo_reversal_link",
            ),
        ),
        migrations.AddConstraint(
            model_name="contributionentry",
            constraint=models.CheckConstraint(
                condition=models.Q(
                    ("kind__in", REVERSAL_KINDS), ("voided", True), _negated=True
                ),
                name="ck_promo_reversal_not_voided",
            ),
        ),
        migrations.AddField(
            model_name="promosend",
            name="recipient_discord_id",
            field=models.CharField(blank=True, default="", max_length=20),
        ),
        migrations.RunPython(
            backfill_recipient_discord_id, migrations.RunPython.noop, elidable=True
        ),
        migrations.AlterField(
            model_name="orglog",
            name="action",
            field=models.CharField(choices=ACTION_CHOICES, max_length=50),
        ),
    ]
