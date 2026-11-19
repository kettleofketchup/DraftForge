from typing import Any

from rest_framework import serializers

from app.models import CustomUser
from opsnotices.models import OpsNotice
from opsnotices.registry import NoticeType, UnknownNoticeType, get_notice_type


class OpsNoticeUserSerializer(serializers.ModelSerializer):
    nickname = serializers.CharField(read_only=True, allow_null=True)
    avatar = serializers.CharField(read_only=True, allow_null=True)

    class Meta:
        model = CustomUser
        fields = ("id", "username", "nickname", "avatar")
        read_only_fields = fields


def _notice_type(key: str) -> NoticeType[Any] | None:
    try:
        return get_notice_type(key)
    except UnknownNoticeType:
        return None


def notice_label(notice: OpsNotice) -> str:
    notice_type = _notice_type(notice.key)
    return notice.key if notice_type is None else notice_type.label


def notice_summary(notice: OpsNotice) -> str:
    notice_type = _notice_type(notice.key)
    if notice_type is None:
        return notice.key
    try:
        summary = notice_type.summary(
            notice_type.payload.model_validate(notice.payload)
        )
    except Exception:
        return notice_type.label
    if not isinstance(summary, str) or not summary:
        return notice_type.label
    return summary


class OpsNoticeSerializer(serializers.ModelSerializer):
    label = serializers.SerializerMethodField()
    summary = serializers.SerializerMethodField()
    event_id = serializers.IntegerField(read_only=True, allow_null=True)
    subject_user = OpsNoticeUserSerializer(read_only=True, allow_null=True)
    actor = OpsNoticeUserSerializer(read_only=True, allow_null=True)

    class Meta:
        model = OpsNotice
        fields = (
            "id",
            "key",
            "label",
            "category",
            "severity",
            "state",
            "summary",
            "event_id",
            "event_name",
            "subject_user",
            "actor",
            "dedupe_key",
            "occurrences",
            "first_seen_at",
            "last_seen_at",
            "closed_at",
            "close_note",
            "delivery_state",
            "payload",
        )
        read_only_fields = fields

    def get_label(self, notice: OpsNotice) -> str:
        return notice_label(notice)

    def get_summary(self, notice: OpsNotice) -> str:
        return notice_summary(notice)
