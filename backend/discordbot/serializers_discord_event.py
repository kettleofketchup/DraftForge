from app.models import CustomUser
from rest_framework import serializers

from .models import (
    DiscordEvent,
    DiscordEventDM,
    DiscordEventLog,
    DiscordEventMsgAnnouncement,
    DiscordEventMsgSignup,
    DiscordMessageLog,
)


class DiscordEventMsgSerializer(serializers.ModelSerializer):
    class Meta:
        fields = [
            "id",
            "channel_id",
            "channel_type",
            "message_id",
            "thread_id",
            "has_posted",
            "message_last_updated",
            "created_at",
            "updated_at",
        ]


class DiscordEventMsgSignupSerializer(DiscordEventMsgSerializer):
    class Meta(DiscordEventMsgSerializer.Meta):
        model = DiscordEventMsgSignup


class DiscordEventMsgAnnouncementSerializer(DiscordEventMsgSerializer):
    class Meta(DiscordEventMsgSerializer.Meta):
        model = DiscordEventMsgAnnouncement


class MessageLogInlineSerializer(serializers.ModelSerializer):
    fired_by_username = serializers.CharField(
        source="fired_by.username", read_only=True, default=None
    )
    fired_by_nickname = serializers.CharField(
        source="fired_by.nickname", read_only=True, default=None
    )

    class Meta:
        model = DiscordMessageLog
        fields = [
            "id",
            "channel_id",
            "source",
            "source_id",
            "discord_message_id",
            "status_code",
            "success",
            "embed_data",
            "response_data",
            "fired_by_username",
            "fired_by_nickname",
            "created_at",
        ]


class DiscordEventLogSerializer(serializers.ModelSerializer):
    category_display = serializers.CharField(
        source="get_category_display", read_only=True
    )
    message_log = MessageLogInlineSerializer(read_only=True)
    # Resolved from the linked CustomUser (by discordId) so the frontend can
    # render the canonical avatar/display name via UserAvatar + DisplayName
    # rather than falling back to a generated image. The lookup map is built
    # once per response in DiscordEventDetailSerializer.to_representation.
    nickname = serializers.SerializerMethodField()
    username = serializers.SerializerMethodField()
    avatar = serializers.SerializerMethodField()

    def _resolved_user(self, obj: DiscordEventLog) -> CustomUser | None:
        user_map: dict[str, CustomUser] = self.context.get("discord_user_map", {})
        return user_map.get(obj.discord_user_id) if obj.discord_user_id else None

    def get_nickname(self, obj: DiscordEventLog) -> str | None:
        user = self._resolved_user(obj)
        return user.nickname if user else None

    def get_username(self, obj: DiscordEventLog) -> str | None:
        user = self._resolved_user(obj)
        return user.username if user else None

    def get_avatar(self, obj: DiscordEventLog) -> str | None:
        user = self._resolved_user(obj)
        return user.avatar if user else None

    class Meta:
        model = DiscordEventLog
        fields = [
            "id",
            "category",
            "category_display",
            "action",
            "target_type",
            "discord_user_id",
            "discord_username",
            "nickname",
            "username",
            "avatar",
            "message_id",
            "status_code",
            "error_message",
            "success",
            "message_log",
            "created_at",
        ]


class DiscordEventDMSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="org_user.user.username", read_only=True)
    nickname = serializers.CharField(source="org_user.user.nickname", read_only=True)
    avatar = serializers.CharField(source="org_user.user.avatar", read_only=True)
    discord_user_id = serializers.CharField(read_only=True)
    can_send = serializers.BooleanField(read_only=True)
    dm_type_display = serializers.CharField(
        source="get_dm_type_display", read_only=True
    )

    class Meta:
        model = DiscordEventDM
        fields = [
            "id",
            "dm_type",
            "dm_type_display",
            "username",
            "nickname",
            "avatar",
            "discord_user_id",
            "can_send",
            "message_id",
            "sent_at",
            "delivered",
            "responded",
            "response_text",
            "responded_at",
            "created_at",
        ]


class DiscordEventDetailSerializer(serializers.ModelSerializer):
    signup_message = DiscordEventMsgSignupSerializer(read_only=True)
    announcement = DiscordEventMsgAnnouncementSerializer(read_only=True)
    logs = DiscordEventLogSerializer(many=True, read_only=True)
    dms = DiscordEventDMSerializer(many=True, read_only=True)

    def to_representation(self, instance: DiscordEvent) -> dict:
        # Batch-resolve the CustomUsers referenced by the logs (by discordId)
        # into a single map so DiscordEventLogSerializer can expose
        # avatar/nickname/username without an N+1 per log entry.
        discord_ids = {
            log.discord_user_id for log in instance.logs.all() if log.discord_user_id
        }
        user_map: dict[str, CustomUser] = {}
        if discord_ids:
            # .nocache(): the join is invalidated only on CustomUser, so a
            # nickname/avatar edit would survive in the joined base_profile row.
            users = (
                CustomUser.objects.filter(discordId__in=discord_ids)
                .select_related("base_profile")
                .nocache()
            )
            user_map = {user.discordId: user for user in users}
        self.context["discord_user_map"] = user_map
        return super().to_representation(instance)

    class Meta:
        model = DiscordEvent
        fields = [
            "id",
            "guild_id",
            "scheduled_event_id",
            "signup_message",
            "announcement",
            "logs",
            "dms",
            "created_at",
            "updated_at",
        ]
