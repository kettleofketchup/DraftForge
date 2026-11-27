from typing import Any

from rest_framework import serializers

from org.api_connections.config import CONFIG_FIELDS
from org.models import OrgApiConnection


class ConnectionSerializer(serializers.ModelSerializer):
    credential_present = serializers.SerializerMethodField()
    inbound_credentials = serializers.SerializerMethodField()

    class Meta:
        model = OrgApiConnection
        fields = (
            "id",
            "config_version",
            *CONFIG_FIELDS,
            "created_at",
            "updated_at",
            "archived_at",
            "created_by",
            "updated_by",
            "credential_present",
            "outbound_credential_owner",
            "outbound_authorizer",
            "outbound_credential_set_at",
            "inbound_credentials",
            "legacy_multi_credential",
            "last_run_summary",
            "last_success_at",
            "last_error_code",
            "next_due_at",
        )
        read_only_fields = fields

    def get_credential_present(self, obj: OrgApiConnection) -> bool:
        return bool(obj.outbound_credential_ciphertext)

    def get_inbound_credentials(self, obj: OrgApiConnection) -> list[dict[str, Any]]:
        return list(
            obj.tokens.order_by("pk").values(
                "id",
                "prefix",
                "user_id",
                "issued_by_id",
                "operations",
                "created_at",
                "revoked_at",
            )
        )
