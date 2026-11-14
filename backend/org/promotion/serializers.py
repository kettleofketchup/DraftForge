from typing import Any

from rest_framework import serializers

from events.models import Event
from org.models import PromoSend, PromoTemplate
from org.promotion.services import MAX_SEND_TEXT


class PromoTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromoTemplate
        fields = ["id", "name", "body", "updated_at"]
        read_only_fields = ["id", "updated_at"]


class PromoEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = ["id", "name", "scheduled_at", "ends_at", "state", "signups_open_at"]
        read_only_fields = fields


class CandidatesQuerySerializer(serializers.Serializer):
    n = serializers.CharField(required=False, allow_blank=True)
    hide_signed_up = serializers.BooleanField(default=True)
    hide_messaged = serializers.BooleanField(default=True)
    q = serializers.CharField(required=False, allow_blank=True, default="")


class RenderRequestSerializer(serializers.Serializer):
    template_id = serializers.IntegerField()
    recipient_id = serializers.IntegerField()


class SendRequestSerializer(serializers.Serializer):
    template_id = serializers.IntegerField(allow_null=True, required=False)
    recipient_id = serializers.IntegerField()
    text = serializers.CharField(
        max_length=MAX_SEND_TEXT, trim_whitespace=False, allow_blank=False
    )


def send_data(send: PromoSend, points_awarded: int | None) -> dict[str, Any]:
    return {
        "id": send.pk,
        "earns_points": send.earns_points,
        "points_awarded": points_awarded,
        "sent_at": serializers.DateTimeField().to_representation(send.sent_at),
    }
