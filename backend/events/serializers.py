import nh3
from rest_framework import serializers

from events.models import Event, EventRepeater, EventSignup, EventTeam


class EventRepeaterSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(
        source="organization.name", read_only=True
    )

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
            "auto_start",
        ]
        read_only_fields = ["id", "created_by", "created_at", "updated_at"]

    def validate_description(self, value):
        return nh3.clean(value) if value else value


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
            "auto_start",
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

    class Meta:
        model = EventSignup
        fields = [
            "id",
            "event",
            "user",
            "username",
            "user_avatar",
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
