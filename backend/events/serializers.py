import nh3
from rest_framework import serializers

from events.models import Event, EventRepeater, EventSignup, EventTeam, OrgEventDefaults


class EventRepeaterSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(
        source="organization.name", read_only=True
    )
    subscriber_count = serializers.IntegerField(read_only=True, default=0)
    is_subscribed = serializers.BooleanField(read_only=True, default=False)

    class Meta:
        model = EventRepeater
        fields = [
            "id",
            "organization",
            "organization_name",
            "name",
            "description",
            "frequency",
            "day_of_week",
            "time_of_day",
            "starts_at",
            "ends_at",
            "generate_days_ahead",
            "is_active",
            "created_by",
            "created_at",
            "updated_at",
            # TournamentTemplate
            "tournament_name",
            "tournament_league",
            "tournament_type",
            "game_type",
            "draft_type",
            "people_per_team",
            "number_of_teams",
            "tournament_date",
            "game_mode",
            "custom_game_name",
            "captains_draft_time",
            "lobby_steam_league_id",
            # EventConfig
            "timezone",
            "min_players",
            "max_players",
            "signup_deadline_hours",
            "allow_team_signups",
            "allow_user_signups",
            "auto_approve",
            "auto_confirm",
            "require_mmr_verified",
            "require_steam_id",
            "require_profile_complete",
            "roll_call_enabled",
            "roll_call_mode",
            # DiscordConfig
            "discord_create_event",
            "discord_sync_signups",
            "discord_event_title",
            "discord_event_description",
            "discord_event_info",
            "discord_signup_reminder",
            "discord_signup_reminder_hours",
            "discord_confirm_attendance",
            "discord_confirm_attendance_hours",
            "discord_profile_reminder",
            "discord_profile_reminder_hours",
            "discord_mark_interested",
            "discord_post_signups",
            "discord_post_signups_channel_id",
            "discord_announcement",
            "discord_announcement_channel_id",
            "discord_announcement_hours",
            "discord_announcement_role_ids",
            "discord_signup_role_ids",
            "discord_notify_new_events",
            "subscriber_count",
            "is_subscribed",
        ]
        read_only_fields = [
            "id",
            "created_by",
            "created_at",
            "updated_at",
            "subscriber_count",
            "is_subscribed",
        ]

    def validate_description(self, value):
        return nh3.clean(value) if value else value

    def validate(self, data):
        game_type = data.get(
            "game_type", self.instance.game_type if self.instance else 1
        )
        game_mode = data.get(
            "game_mode", self.instance.game_mode if self.instance else "normal"
        )
        if game_type != 1 and game_mode in ("captains_mode", "turbo"):
            raise serializers.ValidationError(
                {"game_mode": f"{game_mode} is only available for Dota 2."}
            )
        return data


class EventSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(
        source="organization.name", read_only=True
    )
    # Use annotated fields from queryset (no per-row queries)
    signup_count = serializers.IntegerField(read_only=True, default=0)
    confirmed_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Event
        fields = [
            "id",
            "organization",
            "organization_name",
            "event_repeater",
            "name",
            "description",
            "scheduled_at",
            "signups_open_at",
            "state",
            "tournament",
            "created_by",
            "created_at",
            "updated_at",
            "signup_count",
            "confirmed_count",
            # TournamentTemplate
            "tournament_name",
            "tournament_league",
            "tournament_type",
            "game_type",
            "draft_type",
            "people_per_team",
            "number_of_teams",
            "tournament_date",
            "game_mode",
            "custom_game_name",
            "captains_draft_time",
            "lobby_steam_league_id",
            # EventConfig
            "timezone",
            "min_players",
            "max_players",
            "signup_deadline_hours",
            "allow_team_signups",
            "allow_user_signups",
            "auto_approve",
            "auto_confirm",
            "require_mmr_verified",
            "require_steam_id",
            "require_profile_complete",
            "roll_call_enabled",
            "roll_call_mode",
            # DiscordConfig
            "discord_create_event",
            "discord_sync_signups",
            "discord_event_title",
            "discord_event_description",
            "discord_event_info",
            "discord_signup_reminder",
            "discord_signup_reminder_hours",
            "discord_confirm_attendance",
            "discord_confirm_attendance_hours",
            "discord_profile_reminder",
            "discord_profile_reminder_hours",
            "discord_mark_interested",
            "discord_post_signups",
            "discord_post_signups_channel_id",
            "discord_announcement",
            "discord_announcement_channel_id",
            "discord_announcement_hours",
            "discord_announcement_role_ids",
            "discord_signup_role_ids",
        ]
        read_only_fields = [
            "id",
            "event_repeater",
            "tournament",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def validate_description(self, value):
        return nh3.clean(value) if value else value

    def validate(self, data):
        game_type = data.get(
            "game_type", self.instance.game_type if self.instance else 1
        )
        game_mode = data.get(
            "game_mode", self.instance.game_mode if self.instance else "normal"
        )
        if game_type != 1 and game_mode in ("captains_mode", "turbo"):
            raise serializers.ValidationError(
                {"game_mode": f"{game_mode} is only available for Dota 2."}
            )
        return data


class EventTeamSerializer(serializers.ModelSerializer):
    captain_name = serializers.CharField(source="captain.nickname", read_only=True)
    # Annotated from queryset
    member_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = EventTeam
        fields = [
            "id",
            "event",
            "name",
            "captain",
            "captain_name",
            "member_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]


class EventSignupSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.nickname", read_only=True)
    user_avatar = serializers.CharField(source="user.avatar", read_only=True)
    user_data = serializers.SerializerMethodField()

    class Meta:
        model = EventSignup
        fields = [
            "id",
            "event",
            "user",
            "username",
            "user_avatar",
            "user_data",
            "event_team",
            "signup_type",
            "status",
            "waitlist_position",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "user",
            "status",
            "waitlist_position",
            "created_at",
            "updated_at",
        ]

    def get_user_data(self, obj):
        from app.serializers import TournamentUserSerializer

        return TournamentUserSerializer(obj.user).data


class OrgEventDefaultsSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrgEventDefaults
        fields = [
            "id",
            "organization",
            # TournamentTemplateMixin
            "tournament_name",
            "tournament_league",
            "tournament_type",
            "game_type",
            "draft_type",
            "people_per_team",
            "number_of_teams",
            "game_mode",
            "custom_game_name",
            "captains_draft_time",
            "lobby_steam_league_id",
            # EventConfigMixin
            "timezone",
            "min_players",
            "max_players",
            "signup_deadline_hours",
            "allow_team_signups",
            "allow_user_signups",
            "auto_approve",
            "auto_confirm",
            "require_mmr_verified",
            "require_steam_id",
            "require_profile_complete",
            "roll_call_enabled",
            "roll_call_mode",
            # DiscordEventConfigMixin
            "discord_create_event",
            "discord_sync_signups",
            "discord_event_title",
            "discord_event_description",
            "discord_event_info",
            "discord_signup_reminder",
            "discord_signup_reminder_hours",
            "discord_confirm_attendance",
            "discord_confirm_attendance_hours",
            "discord_profile_reminder",
            "discord_profile_reminder_hours",
            "discord_mark_interested",
            "discord_post_signups",
            "discord_post_signups_channel_id",
            "discord_announcement",
            "discord_announcement_channel_id",
            "discord_announcement_hours",
            "discord_announcement_role_ids",
            "discord_signup_role_ids",
        ]
        read_only_fields = ["id", "organization"]
