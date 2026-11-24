from typing import Any, Final

from rest_framework import serializers

from events.models import Event
from org.mmr import DEFAULT_MMR_BOUNDS
from org.models import PromoSend, PromoTemplate
from org.promotion.recipients import CandidateSource
from org.promotion.services import MAX_SEND_TEXT

MAX_MMR_FILTER: Final[int] = DEFAULT_MMR_BOUNDS[1]


class PromoTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = PromoTemplate
        fields = ["id", "name", "body", "updated_at"]
        read_only_fields = ["id", "updated_at"]


class PromoEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = [
            "id",
            "name",
            "scheduled_at",
            "ends_at",
            "state",
            "signups_open_at",
            "game_type",
        ]
        read_only_fields = fields


class CandidatesQuerySerializer(serializers.Serializer):
    source = serializers.ChoiceField(
        choices=[s.value for s in CandidateSource], default=CandidateSource.RECENT
    )
    n = serializers.CharField(required=False, allow_blank=True)
    days = serializers.CharField(required=False, allow_blank=True)
    hide_signed_up = serializers.BooleanField(default=True)
    hide_messaged = serializers.BooleanField(default=True)
    q = serializers.CharField(required=False, allow_blank=True, default="")
    min_mmr = serializers.IntegerField(
        required=False, allow_null=True, min_value=0, max_value=MAX_MMR_FILTER
    )
    max_mmr = serializers.IntegerField(
        required=False, allow_null=True, min_value=0, max_value=MAX_MMR_FILTER
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        low, high = attrs.get("min_mmr"), attrs.get("max_mmr")
        if low is not None and high is not None and low > high:
            raise serializers.ValidationError(
                {"max_mmr": ["must be at least the minimum MMR"]}
            )
        return attrs


class DiscordMemberRequestSerializer(serializers.Serializer):
    discord_id = serializers.RegexField(r"^\d{1,20}$")


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
