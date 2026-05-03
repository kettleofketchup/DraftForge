import nh3
from rest_framework import serializers

from events.models import (
    Event,
    EventRepeater,
    EventSignup,
    EventTeam,
    OrgEventDefaults,
    RepeaterSubscription,
)


class EventRepeaterSlimSerializer(serializers.ModelSerializer):
    """Lightweight serializer for repeater list views (events page Series tab)."""

    organization_name = serializers.CharField(
        source="organization.name", read_only=True
    )
    subscriber_count = serializers.IntegerField(read_only=True, default=0)
    next_event_date = serializers.DateTimeField(read_only=True, default=None)

    class Meta:
        model = EventRepeater
        fields = [
            "id",
            "organization",
            "organization_name",
            "name",
            "frequency",
            "day_of_week",
            "time_of_day",
            "timezone",
            "is_active",
            "subscriber_count",
            "next_event_date",
        ]


class EventRepeaterSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(
        source="organization.name", read_only=True
    )
    subscriber_count = serializers.IntegerField(read_only=True, default=0)
    is_subscribed = serializers.BooleanField(read_only=True, default=False)
    next_event_date = serializers.DateTimeField(read_only=True, default=None)

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
            "allow_active_mmr",
            "allow_previous_rank",
            "allow_battlecup_rating",
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
            "discord_require_rank_screenshot",
            "discord_require_battlecup_screenshot",
            "min_mmr",
            "discord_notify_new_events",
            # DiscordTournamentConfig
            "auto_create_hero_drafts",
            "discord_send_draft_link",
            "discord_send_herodraft_link",
            "subscriber_count",
            "is_subscribed",
            "next_event_date",
        ]
        read_only_fields = [
            "id",
            "created_by",
            "created_at",
            "updated_at",
            "subscriber_count",
            "is_subscribed",
            "next_event_date",
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


class EventSlimSerializer(serializers.ModelSerializer):
    """Lightweight serializer for event list views — only fields needed for cards."""

    organization_name = serializers.CharField(
        source="organization.name", read_only=True
    )
    signup_count = serializers.IntegerField(read_only=True, default=0)
    confirmed_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Event
        fields = [
            "id",
            "organization",
            "organization_name",
            "name",
            "scheduled_at",
            "state",
            "game_type",
            "tournament_name",
            "tournament_league",
            "tournament_type",
            "draft_type",
            "people_per_team",
            "number_of_teams",
            "signup_count",
            "confirmed_count",
            "event_repeater",
            # Reminder fields needed by fire_due_reminders — see
            # events/scheduling/registry.py REMINDERS list. Test
            # tests/test_serializers.py::EventSlimSerializerReminderFieldsTest
            # asserts these stay in sync with the registry.
            "discord_announcement",
            "discord_announcement_hours",
            "discord_announcement_channel_id",
            "discord_signup_reminder",
            "discord_signup_reminder_hours",
            "discord_confirm_attendance",
            "discord_confirm_attendance_hours",
            "discord_profile_reminder",
            "discord_profile_reminder_hours",
        ]


class EventSerializer(serializers.ModelSerializer):
    organization_name = serializers.CharField(
        source="organization.name", read_only=True
    )
    event_repeater_name = serializers.CharField(
        source="event_repeater.name", read_only=True, default=None
    )
    # Use annotated fields from queryset (no per-row queries)
    signup_count = serializers.IntegerField(read_only=True, default=0)
    confirmed_count = serializers.IntegerField(read_only=True, default=0)
    # Per-request override; populated in the view layer AFTER the cached payload
    # is resolved, so the cache stays user-agnostic.
    user_can_manage = serializers.BooleanField(read_only=True, default=False)

    class Meta:
        model = Event
        fields = [
            "id",
            "organization",
            "organization_name",
            "event_repeater",
            "event_repeater_name",
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
            "allow_active_mmr",
            "allow_previous_rank",
            "allow_battlecup_rating",
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
            "discord_require_rank_screenshot",
            "discord_require_battlecup_screenshot",
            "min_mmr",
            # DiscordTournamentConfig
            "auto_create_hero_drafts",
            "discord_send_draft_link",
            "discord_send_herodraft_link",
            "user_can_manage",
        ]
        read_only_fields = [
            "id",
            "event_repeater",
            "tournament",
            "created_by",
            "created_at",
            "updated_at",
        ]

    def validate_tournament_league(self, value):
        if value is None:
            return value
        org_id = (
            self.instance.organization_id
            if self.instance is not None
            else self.initial_data.get("organization")
        )
        if org_id is not None and value.organization_id != org_id:
            raise serializers.ValidationError(
                "League must belong to the event's organization."
            )
        return value

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

        # Single events have no subscriber list — discord_signup_reminder DMs
        # subscribed users, which is a series-level concept on EventRepeater.
        # Reject signup_reminder=True on events without a repeater.
        repeater = data.get(
            "event_repeater",
            self.instance.event_repeater if self.instance else None,
        )
        signup_reminder = data.get(
            "discord_signup_reminder",
            self.instance.discord_signup_reminder if self.instance else False,
        )
        if repeater is None and signup_reminder:
            raise serializers.ValidationError(
                {
                    "discord_signup_reminder": (
                        "Signup reminder DMs require a recurring event series — "
                        "single events have no subscribers."
                    )
                }
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
    dota_profile = serializers.SerializerMethodField()
    org_user_mmr = serializers.SerializerMethodField()
    suggested_mmr = serializers.SerializerMethodField()
    suggested_mmr_range = serializers.SerializerMethodField()
    suggested_mmr_range_source = serializers.SerializerMethodField()

    class Meta:
        model = EventSignup
        fields = [
            "id",
            "event",
            "user",
            "username",
            "user_avatar",
            "user_data",
            "dota_profile",
            "org_user_mmr",
            "suggested_mmr",
            "suggested_mmr_range",
            "suggested_mmr_range_source",
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
        from app.models import CustomUser
        from app.serializers import TournamentUserSerializer, _serialize_user_with_mmr

        # Resolve user — obj.user may be a SimpleLazyObject from request.user
        # which breaks type(user).objects calls. Always fetch a real instance.
        user = CustomUser.objects.get(pk=obj.user.pk)

        if not obj.event.tournament:
            return TournamentUserSerializer(user).data
        return _serialize_user_with_mmr(user, obj.event.tournament)

    def get_dota_profile(self, obj):
        """Return DotaProfile data if the user has one for this event's org."""
        from org.models import OrgUser
        from org.models_profiles import PlayerDotaProfile

        try:
            org_user = OrgUser.objects.get(
                user=obj.user, organization=obj.event.organization
            )
            profile = PlayerDotaProfile.objects.get(org_user=org_user)
            return {
                "positions": {
                    "pos_1": profile.pos_1,
                    "pos_2": profile.pos_2,
                    "pos_3": profile.pos_3,
                    "pos_4": profile.pos_4,
                    "pos_5": profile.pos_5,
                },
                "rank_status": profile.rank_status,
                "rank_medal": profile.rank_medal,
                "mmr": profile.mmr,
                "rank_screenshot": profile.rank_screenshot or None,
                "battlecup_screenshot": profile.battlecup_screenshot or None,
                "battle_cup_tier": profile.battle_cup_tier,
            }
        except (OrgUser.DoesNotExist, PlayerDotaProfile.DoesNotExist):
            return None

    def get_org_user_mmr(self, obj):
        """Return the OrgUser MMR for this user in the event's org.

        We surface any non-zero MMR for display purposes regardless of the
        has_active_dota_mmr flag — that flag is for requirements gating
        (auto-approve), not for whether the value is shown.
        """
        from org.models import OrgUser

        try:
            org_user = OrgUser.objects.get(
                user=obj.user, organization=obj.event.organization
            )
        except OrgUser.DoesNotExist:
            return None
        return org_user.mmr if org_user.mmr else None

    def get_suggested_mmr(self, obj):
        return self._mmr_suggestion(obj)["default"]

    def get_suggested_mmr_range(self, obj):
        return self._mmr_suggestion(obj)["range"]

    def get_suggested_mmr_range_source(self, obj):
        return self._mmr_suggestion(obj)["range_source"]

    def _mmr_suggestion(self, obj):
        """Memoize the suggest_mmr result per signup instance."""
        if hasattr(obj, "_mmr_suggestion_cache"):
            return obj._mmr_suggestion_cache

        from events.mmr_suggestions import suggest_mmr
        from org.models import OrgUser
        from org.models_profiles import PlayerDotaProfile

        profile = None
        prior_mmr = None
        try:
            org_user = OrgUser.objects.get(
                user=obj.user, organization=obj.event.organization
            )
            prior_mmr = org_user.mmr if org_user.mmr else None
            try:
                profile = PlayerDotaProfile.objects.get(org_user=org_user)
            except PlayerDotaProfile.DoesNotExist:
                profile = None
        except OrgUser.DoesNotExist:
            pass

        obj._mmr_suggestion_cache = suggest_mmr(profile, prior_mmr)
        return obj._mmr_suggestion_cache


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
            "allow_active_mmr",
            "allow_previous_rank",
            "allow_battlecup_rating",
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
            "discord_require_rank_screenshot",
            "discord_require_battlecup_screenshot",
            "min_mmr",
            # DiscordTournamentConfig
            "auto_create_hero_drafts",
            "discord_send_draft_link",
            "discord_send_herodraft_link",
        ]
        read_only_fields = ["id", "organization"]


class RepeaterSubscriptionSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    nickname = serializers.CharField(source="user.nickname", read_only=True)
    discordId = serializers.CharField(source="user.discordId", read_only=True)
    avatar = serializers.CharField(source="user.avatar", read_only=True)

    class Meta:
        model = RepeaterSubscription
        fields = ["id", "username", "nickname", "discordId", "avatar", "created_at"]
