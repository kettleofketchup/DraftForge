from datetime import datetime
from typing import Any

import nh3
from django.core.exceptions import ValidationError as DjangoValidationError
from django.utils import timezone
from rest_framework import serializers

from app.auth import InternalServiceUser
from app.display_names import user_display_name
from app.models import CustomUser, League, Organization
from app.permissions_org import (
    can_view_org_members,
    check_lobby_steam_league_id,
    has_event_staff_access,
    request_user,
)
from app.serializers import TournamentUserSerializer, _serialize_users_with_mmr
from app.user_cache import serialize_users_core
from events.capacity import seat_holding_statuses
from events.constants import EventState, SignupOpenMode
from events.mmr_suggestions import suggest_mmr
from events.models import (
    Event,
    EventRepeater,
    EventSignup,
    EventTeam,
    OrgEventDefaults,
    RepeaterSubscription,
)
from events.services import (
    DISCORD_CONFIG_FIELDS,
    DISCORD_TOURNAMENT_TEMPLATE_FIELDS,
    DOTA_LOBBY_CONFIG_FIELDS,
    EVENT_CONFIG_FIELDS,
    TOURNAMENT_TEMPLATE_FIELDS,
)
from events.signup_schedule import (
    MAX_SIGNUPS_OPEN_HOURS_BEFORE,
    SIGNUP_OPEN_POLICY_FIELDS,
    apply_signup_open_policy,
    policy_from_explicit_open_at,
)
from lobby.passwords import MAX_LENGTH as LOBBY_PASSWORD_MAX_LENGTH
from lobby.passwords import PasswordMode, validate_password
from org.display_names import guild_nicknames, org_nicknames_public
from org.models import OrgUser
from org.models_profiles import PlayerDotaProfile

# The lobby password is write-only on every events serializer: event and
# series payloads are cached, public and handed to Celery. Staff and
# registered players read it from the lobby-password endpoints.
LOBBY_PASSWORD_FIELD_KWARGS = {
    "write_only": True,
    "required": False,
    "allow_blank": True,
    "max_length": LOBBY_PASSWORD_MAX_LENGTH,
    "trim_whitespace": False,
}


def _valid_fixed_password(value: str) -> str:
    try:
        return validate_password(value)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({"dota_lobby_password": exc.messages})


DRAFT_TIME_KWARGS = {"min_value": 1}
GRACE_TIME_MS_KWARGS = {"min_value": 1000}
RESERVE_TIME_MS_KWARGS = {"min_value": 0}
TIMER_FIELD_KWARGS = {
    "draft_grace_time_ms": GRACE_TIME_MS_KWARGS,
    "draft_reserve_time_ms": RESERVE_TIME_MS_KWARGS,
    "hero_grace_time_ms": GRACE_TIME_MS_KWARGS,
    "hero_reserve_time_ms": RESERVE_TIME_MS_KWARGS,
}
SIGNUPS_OPEN_HOURS_KWARGS = {"max_value": MAX_SIGNUPS_OPEN_HOURS_BEFORE}


class LobbySteamLeagueMixin:
    """Gate a changed lobby_steam_league_id; ``source`` holds the current or
    inherited values (instance, or the series for a one-off)."""

    def check_lobby_steam_league(
        self, data: dict, source: Event | EventRepeater | OrgEventDefaults | None
    ) -> None:
        if "lobby_steam_league_id" not in data:
            return
        value = data["lobby_steam_league_id"]
        if source is not None and value == source.lobby_steam_league_id:
            return
        check_lobby_steam_league_id(
            request_user(self.context),
            value,
            data.get("tournament_league", getattr(source, "tournament_league", None)),
        )


class TournamentLeagueOrgMixin:
    """Reject a tournament_league owned by another organization.

    Resolves the org from the instance on update, else from the incoming body.
    Neither available (create with an org the view supplies later) — skip.
    """

    def validate_tournament_league(self, value: League | None) -> League | None:
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


class EventRepeaterSerializer(
    LobbySteamLeagueMixin, TournamentLeagueOrgMixin, serializers.ModelSerializer
):
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
            "draft_timer_enabled",
            "draft_grace_time_ms",
            "draft_reserve_time_ms",
            "draft_timeout_action",
            "hero_timer_enabled",
            "hero_grace_time_ms",
            "hero_reserve_time_ms",
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
            "signup_open_mode",
            "signups_open_hours_before",
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
            # DotaLobbyConfig
            "dota_lobby_mode",
            "dota_lobby_launch",
            "dota_lobby_region",
            "discord_send_lobby_info",
            "dota_lobby_password_mode",
            "dota_lobby_password",
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
        extra_kwargs = {
            "dota_lobby_password": LOBBY_PASSWORD_FIELD_KWARGS,
            "captains_draft_time": DRAFT_TIME_KWARGS,
            **TIMER_FIELD_KWARGS,
            "signups_open_hours_before": SIGNUPS_OPEN_HOURS_KWARGS,
        }

    def validate_description(self, value: str | None) -> str | None:
        return nh3.clean(value) if value else value

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
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
        self.check_lobby_steam_league(data, self.instance)
        # Fixed: the series stores the password. Random: it stores none,
        # each event generates its own.
        mode = data.get(
            "dota_lobby_password_mode",
            (
                self.instance.dota_lobby_password_mode
                if self.instance
                else PasswordMode.RANDOM
            ),
        )
        if mode == PasswordMode.FIXED:
            current = self.instance.dota_lobby_password if self.instance else ""
            data["dota_lobby_password"] = _valid_fixed_password(
                data.get("dota_lobby_password", current)
            )
        else:
            data["dota_lobby_password"] = ""
        return data


class EventStaffUserSerializer(serializers.ModelSerializer):
    avatarUrl = serializers.CharField(read_only=True)
    guildNickname = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            "pk",
            "username",
            "nickname",
            "discordNickname",
            "guildNickname",
            "avatarUrl",
        ]
        read_only_fields = fields

    def get_guildNickname(self, obj: CustomUser) -> str | None:
        nicks: dict[int, str | None] = self.context.get("_staff_guild_nicknames", {})
        return nicks.get(obj.pk)


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
            "ends_at",
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
            "is_off_schedule",
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
        read_only_fields = ["ends_at"]


class EventSerializer(
    LobbySteamLeagueMixin, TournamentLeagueOrgMixin, serializers.ModelSerializer
):
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
    user_can_manage_event_staff = serializers.BooleanField(
        read_only=True, default=False
    )
    host = EventStaffUserSerializer(read_only=True)
    helpers = EventStaffUserSerializer(many=True, read_only=True)

    def to_representation(self, instance: Event) -> dict[str, Any]:
        nicks: dict[int, str | None] = {}
        org_id = instance.organization_id
        if org_nicknames_public(org_id):
            staff_ids = [user.pk for user in instance.helpers.all()]
            if instance.host_id is not None:
                staff_ids.append(instance.host_id)
            nicks = guild_nicknames(org_id, staff_ids)
        self.context["_staff_guild_nicknames"] = nicks
        return super().to_representation(instance)

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
            "ends_at",
            "signups_open_at",
            "state",
            "host",
            "helpers",
            "contributions_awarded_at",
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
            "draft_timer_enabled",
            "draft_grace_time_ms",
            "draft_reserve_time_ms",
            "draft_timeout_action",
            "hero_timer_enabled",
            "hero_grace_time_ms",
            "hero_reserve_time_ms",
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
            "signup_open_mode",
            "signups_open_hours_before",
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
            # DotaLobbyConfig
            "dota_lobby_mode",
            "dota_lobby_launch",
            "dota_lobby_region",
            "discord_send_lobby_info",
            "dota_lobby_password_mode",
            "dota_lobby_password",
            "user_can_manage",
            "user_can_manage_event_staff",
            "is_off_schedule",
        ]
        read_only_fields = [
            "id",
            "state",
            "contributions_awarded_at",
            "event_repeater",
            "is_off_schedule",
            "tournament",
            "created_by",
            "created_at",
            "updated_at",
        ]
        extra_kwargs = {
            "dota_lobby_password": LOBBY_PASSWORD_FIELD_KWARGS,
            "captains_draft_time": DRAFT_TIME_KWARGS,
            **TIMER_FIELD_KWARGS,
            "signups_open_hours_before": SIGNUPS_OPEN_HOURS_KWARGS,
        }

    def create(self, validated_data: dict[str, Any]) -> Event:
        if self._takes_legacy_open_at(validated_data):
            validated_data.update(
                policy_from_explicit_open_at(
                    validated_data["scheduled_at"], validated_data["signups_open_at"]
                )
            )
            return super().create(validated_data)
        defaults = OrgEventDefaults.objects.filter(
            organization=validated_data["organization"]
        ).first()
        if defaults is not None:
            for field in SIGNUP_OPEN_POLICY_FIELDS:
                validated_data.setdefault(field, getattr(defaults, field))
        probe = Event(
            scheduled_at=validated_data["scheduled_at"],
            **{
                f: validated_data[f]
                for f in SIGNUP_OPEN_POLICY_FIELDS
                if f in validated_data
            },
        )
        apply_signup_open_policy(probe, timezone.now())
        validated_data["signups_open_at"] = probe.signups_open_at
        return super().create(validated_data)

    def update(self, instance: Event, validated_data: dict[str, Any]) -> Event:
        before = {
            f: getattr(instance, f)
            for f in (*SIGNUP_OPEN_POLICY_FIELDS, "scheduled_at")
        }
        upcoming = instance.state == EventState.UPCOMING
        legacy = upcoming and self._takes_legacy_open_at(validated_data)
        if legacy:
            validated_data.update(
                policy_from_explicit_open_at(
                    validated_data.get("scheduled_at", instance.scheduled_at),
                    validated_data["signups_open_at"],
                )
            )
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        update_fields = [*validated_data, "updated_at"]
        if upcoming and not legacy:
            policy_changed = any(
                before[f] != getattr(instance, f) for f in SIGNUP_OPEN_POLICY_FIELDS
            )
            moved = before["scheduled_at"] != instance.scheduled_at
            # A manual event keeps a pre-policy hand-set open time on reschedule.
            if policy_changed or (
                moved and instance.signup_open_mode != SignupOpenMode.MANUAL
            ):
                apply_signup_open_policy(instance, timezone.now())
                if "signups_open_at" not in update_fields:
                    update_fields.append("signups_open_at")
        instance.save(update_fields=update_fields)
        return instance

    @staticmethod
    def _takes_legacy_open_at(validated_data: dict[str, Any]) -> bool:
        return (
            "signups_open_at" in validated_data
            and "signup_open_mode" not in validated_data
        )

    def validate_description(self, value: str | None) -> str | None:
        return nh3.clean(value) if value else value

    def validate_organization(self, value: Organization) -> Organization:
        if self.instance is not None and value.pk != self.instance.organization_id:
            raise serializers.ValidationError(
                "An event cannot move to another organization."
            )
        return value

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
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
        self.check_lobby_steam_league(data, self.instance)

        # Single events have no subscriber list — discord_signup_reminder DMs
        # subscribed users, which is a series-level concept on EventRepeater.
        # Reject signup_reminder=True on events without a repeater. Only run
        # this check when the request actually touches one of those fields
        # (or on create) — otherwise pre-existing invalid state would block
        # every unrelated PATCH on the event, even one that just changes the
        # name.
        is_create = self.instance is None
        touches_relevant_fields = (
            "discord_signup_reminder" in data or "event_repeater" in data
        )
        if is_create or touches_relevant_fields:
            repeater = data.get(
                "event_repeater",
                self.instance.event_repeater if self.instance else None,
            )
            # On create, fall back to False when the field is absent — matches
            # original behavior so callers that don't explicitly set this field
            # aren't surprised. The model default of True remains a latent
            # inconsistency (events get saved with reminder=True but the
            # validator silently allows it on create); fix is out of scope here
            # since correcting it would require a model migration + sweep of
            # ~10 Playwright tests that don't pass this field. Tracked
            # separately. The validator still rejects explicit signup_reminder=True
            # on a single event.
            default_reminder = (
                self.instance.discord_signup_reminder if self.instance else False
            )
            signup_reminder = data.get("discord_signup_reminder", default_reminder)
            if repeater is None and signup_reminder:
                raise serializers.ValidationError(
                    {
                        "discord_signup_reminder": (
                            "Signup reminder DMs require a recurring event series — "
                            "single events have no subscribers."
                        )
                    }
                )
        self._validate_ends_at(data)
        self._validate_lobby_password(data)
        return data

    def _validate_ends_at(self, data: dict[str, Any]) -> None:
        if "ends_at" not in data and "scheduled_at" not in data:
            return
        instance = self.instance
        ends_at = data.get("ends_at", instance.ends_at if instance else None)
        if ends_at is None:
            return
        scheduled_at = data.get(
            "scheduled_at", instance.scheduled_at if instance else None
        )
        if scheduled_at is not None and ends_at <= scheduled_at:
            raise serializers.ValidationError(
                {"ends_at": "End time must be after the start time."}
            )

    def _validate_lobby_password(self, data: dict[str, Any]) -> None:
        """Fixed needs a valid password; random keeps or generates one.

        Switching to random (or a random event without a password) leaves the
        password empty, so Event.save generates one. A random event keeps its
        password otherwise; regenerating is a separate staff action.
        """
        instance = self.instance
        previous_mode = instance.dota_lobby_password_mode if instance else None
        mode = data.get(
            "dota_lobby_password_mode", previous_mode or PasswordMode.RANDOM
        )
        if mode == PasswordMode.FIXED:
            current = (
                instance.dota_lobby_password
                if instance and previous_mode == PasswordMode.FIXED
                else ""
            )
            data["dota_lobby_password"] = _valid_fixed_password(
                data.get("dota_lobby_password", current)
            )
        elif (
            instance is not None
            and previous_mode == PasswordMode.RANDOM
            and instance.dota_lobby_password
        ):
            data.pop("dota_lobby_password", None)
        else:
            data["dota_lobby_password"] = ""


class EventTeamSerializer(serializers.ModelSerializer):
    captain_name = serializers.SerializerMethodField()
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

    def _viewer_sees_org_members(self, org_id: int) -> bool:
        memo: dict[int, bool] = self.context.setdefault("_team_org_visible", {})
        if org_id not in memo:
            request = self.context.get("request")
            memo[org_id] = request is not None and can_view_org_members(
                request.user, org_id
            )
        return memo[org_id]

    def _captain_nicknames(self, obj: EventTeam) -> dict[int, str | None]:
        org_id = obj.event.organization_id
        memo: dict[int, dict[int, str | None]] = self.context.setdefault(
            "_team_captain_nicknames", {}
        )
        nicks = memo.setdefault(org_id, {})
        if obj.captain_id not in nicks:
            parent = self.parent
            rows = (
                list(parent.instance)
                if isinstance(parent, serializers.ListSerializer) and parent.instance
                else [obj]
            )
            ids = {
                row.captain_id for row in rows if row.event.organization_id == org_id
            } | {obj.captain_id}
            ids -= nicks.keys()
            found = guild_nicknames(org_id, ids)
            nicks.update({user_id: found.get(user_id) for user_id in ids})
        return nicks

    def get_captain_name(self, obj: EventTeam) -> str:
        nick = None
        if self._viewer_sees_org_members(obj.event.organization_id):
            nick = self._captain_nicknames(obj).get(obj.captain_id)
        return user_display_name(obj.captain, guild_nickname=nick)


class EventSignupSerializer(serializers.ModelSerializer):
    username = serializers.SerializerMethodField()
    user_avatar = serializers.CharField(source="user.avatar", read_only=True)
    user_data = serializers.SerializerMethodField()
    dota_profile = serializers.SerializerMethodField()
    org_user_mmr = serializers.SerializerMethodField()
    org_user_pk = serializers.SerializerMethodField()
    organization = serializers.IntegerField(
        source="event.organization_id", read_only=True
    )
    suggested_mmr = serializers.SerializerMethodField()
    suggested_mmr_range = serializers.SerializerMethodField()
    suggested_mmr_range_source = serializers.SerializerMethodField()
    holds_seat = serializers.SerializerMethodField()
    unmet_requirements = serializers.SerializerMethodField()

    class Meta:
        model = EventSignup
        fields = [
            "id",
            "event",
            "organization",
            "user",
            "username",
            "user_avatar",
            "user_data",
            "dota_profile",
            "org_user_mmr",
            "org_user_pk",
            "suggested_mmr",
            "suggested_mmr_range",
            "suggested_mmr_range_source",
            "event_team",
            "signup_type",
            "status",
            "waitlist_position",
            "holds_seat",
            "unmet_requirements",
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

    def _batch(self, obj: EventSignup) -> list[EventSignup]:
        parent = self.parent
        if isinstance(parent, serializers.ListSerializer) and parent.instance:
            rows = list(parent.instance)
            if any(row is obj for row in rows):
                return rows
        return [obj]

    def _org_user(self, obj: EventSignup) -> OrgUser | None:
        """The signup user's OrgUser in the event's org, bulk-loaded per list."""
        memo: dict[tuple[int, int], OrgUser | None] = self.context.setdefault(
            "_signup_org_users", {}
        )
        key = (obj.user_id, obj.event.organization_id)
        if key not in memo:
            keys = {(r.user_id, r.event.organization_id) for r in self._batch(obj)}
            keys = (keys - memo.keys()) | {key}
            found = (
                OrgUser.objects.nocache()
                .filter(
                    user_id__in={user_id for user_id, _ in keys},
                    organization_id__in={org_id for _, org_id in keys},
                )
                .select_related("dota_profile")
            )
            for org_user in found:
                pair = (org_user.user_id, org_user.organization_id)
                if pair in keys:
                    memo[pair] = org_user
            for pair in keys:
                memo.setdefault(pair, None)
        return memo[key]

    def _dota_profile(self, obj: EventSignup) -> PlayerDotaProfile | None:
        org_user = self._org_user(obj)
        if org_user is None:
            return None
        try:
            return org_user.dota_profile
        except PlayerDotaProfile.DoesNotExist:
            return None

    def _user_payload(self, obj: EventSignup) -> dict[str, Any]:
        """Serialized user (org-shaped for tournament events), bulk per list."""
        memo: dict[int | None, dict[int, dict[str, Any]]] = self.context.setdefault(
            "_signup_user_payloads", {}
        )
        tournament_id = obj.event.tournament_id
        payloads = memo.setdefault(tournament_id, {})
        if obj.user_id not in payloads:
            user_ids = {
                r.user_id
                for r in self._batch(obj)
                if r.event.tournament_id == tournament_id
            } - payloads.keys()
            user_ids.add(obj.user_id)
            if tournament_id is None:
                payloads.update(serialize_users_core(user_ids))
            else:
                rows = _serialize_users_with_mmr(
                    CustomUser.objects.filter(pk__in=user_ids), obj.event.tournament
                )
                payloads.update({row["pk"]: row for row in rows})
            for user_id in user_ids - payloads.keys():
                payloads[user_id] = TournamentUserSerializer(
                    CustomUser.objects.get(pk=user_id)
                ).data
        return payloads[obj.user_id]

    def get_username(self, obj: EventSignup) -> str:
        org_user = self._org_user(obj)
        nick = (
            org_user.guild_nickname
            if org_user and self._viewer_sees_org_mmr(obj)
            else None
        )
        return user_display_name(obj.user, guild_nickname=nick)

    def get_user_data(self, obj: EventSignup) -> dict[str, Any]:
        data = dict(self._user_payload(obj))
        if obj.event.tournament_id is None:
            org_user = self._org_user(obj)
            data["guildNickname"] = org_user.guild_nickname if org_user else None
        if not self._viewer_sees_org_mmr(obj):
            for key in ("guildNickname", "mmr", "league_mmr"):
                data.pop(key, None)
        return data

    def get_holds_seat(self, signup: EventSignup) -> bool:
        return signup.status in seat_holding_statuses(signup.event)

    def get_unmet_requirements(self, signup: EventSignup) -> list[str]:
        """Visible to the signup owner and event staff only."""
        request = self.context.get("request")
        if request is None:
            return []
        user = request.user
        if not user.is_authenticated:
            return []
        if user.pk != signup.user_id:
            cache: dict[int, bool] = self.context.setdefault("_event_staff", {})
            if signup.event_id not in cache:
                cache[signup.event_id] = has_event_staff_access(user, signup.event)
            if not cache[signup.event_id]:
                return []
        return list(signup.unmet_requirements or [])

    def get_dota_profile(self, obj: EventSignup) -> dict[str, Any] | None:
        """Return DotaProfile data if the user has one for this event's org."""
        profile = self._dota_profile(obj)
        if profile is None:
            return None
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

    def get_org_user_mmr(self, obj: EventSignup) -> int | None:
        """Return the OrgUser MMR for this user in the event's org.

        We surface any non-zero MMR for display purposes regardless of the
        has_active_dota_mmr flag — that flag is for requirements gating
        (auto-approve), not for whether the value is shown. Hidden from
        viewers who may not see the org's member list.
        """
        if not self._viewer_sees_org_mmr(obj):
            return None
        org_user = self._org_user(obj)
        return org_user.mmr if org_user and org_user.mmr else None

    def _viewer_sees_org_mmr(self, obj: EventSignup) -> bool:
        request = self.context.get("request")
        if request is None:
            return False
        user = request.user
        if isinstance(user, InternalServiceUser):
            return True
        if user.is_authenticated and user.pk == obj.user_id:
            return True
        cache: dict[int, bool] = self.context.setdefault("_org_mmr_visible", {})
        org_id = obj.event.organization_id
        if org_id not in cache:
            cache[org_id] = can_view_org_members(user, org_id)
        return cache[org_id]

    def get_org_user_pk(self, obj: EventSignup) -> int | None:
        """Return the OrgUser pk for this user in the event's org.

        Frontend caches this alongside org_user_mmr so the user-cache entry's
        org-scoped slot can be hydrated without a separate org-users fetch.
        """
        org_user = self._org_user(obj)
        return org_user.pk if org_user else None

    def get_suggested_mmr(self, obj: EventSignup) -> int:
        return self._mmr_suggestion(obj)["default"]

    def get_suggested_mmr_range(self, obj: EventSignup) -> list[int]:
        return self._mmr_suggestion(obj)["range"]

    def get_suggested_mmr_range_source(self, obj: EventSignup) -> str:
        return self._mmr_suggestion(obj)["range_source"]

    def _mmr_suggestion(self, obj: EventSignup) -> dict[str, Any]:
        """Memoize the suggest_mmr result per signup instance."""
        if hasattr(obj, "_mmr_suggestion_cache"):
            return obj._mmr_suggestion_cache
        org_user = self._org_user(obj)
        prior_mmr = org_user.mmr if org_user and org_user.mmr else None
        obj._mmr_suggestion_cache = suggest_mmr(self._dota_profile(obj), prior_mmr)
        return obj._mmr_suggestion_cache


class OrgEventDefaultsSerializer(
    LobbySteamLeagueMixin, TournamentLeagueOrgMixin, serializers.ModelSerializer
):
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
            "draft_timer_enabled",
            "draft_grace_time_ms",
            "draft_reserve_time_ms",
            "draft_timeout_action",
            "hero_timer_enabled",
            "hero_grace_time_ms",
            "hero_reserve_time_ms",
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
            "signup_open_mode",
            "signups_open_hours_before",
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
        extra_kwargs = {
            "captains_draft_time": DRAFT_TIME_KWARGS,
            **TIMER_FIELD_KWARGS,
            "signups_open_hours_before": SIGNUPS_OPEN_HOURS_KWARGS,
        }

    def validate(self, data: dict) -> dict:
        self.check_lobby_steam_league(data, self.instance)
        return data


class RepeaterSubscriptionSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source="user.username", read_only=True)
    nickname = serializers.CharField(source="user.nickname", read_only=True)
    discordNickname = serializers.CharField(
        source="user.discordNickname", read_only=True
    )
    discordId = serializers.CharField(source="user.discordId", read_only=True)
    avatar = serializers.CharField(source="user.avatar", read_only=True)

    class Meta:
        model = RepeaterSubscription
        fields = [
            "id",
            "username",
            "nickname",
            "discordNickname",
            "discordId",
            "avatar",
            "created_at",
        ]


ONE_OFF_OVERRIDE_FIELDS = (
    ["name", "description"]
    + TOURNAMENT_TEMPLATE_FIELDS
    + EVENT_CONFIG_FIELDS
    + DISCORD_CONFIG_FIELDS
    + DISCORD_TOURNAMENT_TEMPLATE_FIELDS
    + DOTA_LOBBY_CONFIG_FIELDS
    + ["dota_lobby_password"]
)


class OneOffEventCreateSerializer(LobbySteamLeagueMixin, serializers.ModelSerializer):
    """Validates the body of POST /events/repeaters/<pk>/create-event/.

    Every config key is optional: an absent key means "inherit from the series",
    so nothing here may carry a `default` — that would clobber the inherited value.
    Never call .save() on this serializer; the view calls create_off_schedule_event.
    """

    OVERRIDE_FIELDS = ONE_OFF_OVERRIDE_FIELDS

    scheduled_at = serializers.DateTimeField()
    ends_at = serializers.DateTimeField(required=False, allow_null=True)
    open_signups = serializers.BooleanField(required=False, default=False)

    class Meta:
        model = Event
        fields = ONE_OFF_OVERRIDE_FIELDS + ["scheduled_at", "ends_at", "open_signups"]
        extra_kwargs = {
            **{name: {"required": False} for name in ONE_OFF_OVERRIDE_FIELDS},
            "dota_lobby_password": LOBBY_PASSWORD_FIELD_KWARGS,
            "captains_draft_time": {"required": False, **DRAFT_TIME_KWARGS},
            **{
                name: {"required": False, **kwargs}
                for name, kwargs in TIMER_FIELD_KWARGS.items()
            },
            "signups_open_hours_before": {
                "required": False,
                **SIGNUPS_OPEN_HOURS_KWARGS,
            },
        }

    def validate_scheduled_at(self, value: datetime) -> datetime:
        if value <= timezone.now():
            raise serializers.ValidationError("Scheduled time must be in the future.")
        repeater = self.context["repeater"]
        if repeater.ends_at and value.date() > repeater.ends_at:
            raise serializers.ValidationError(
                "Scheduled time is after this series' end date."
            )
        return value

    def validate_tournament_league(self, value: League | None) -> League | None:
        repeater = self.context["repeater"]
        if value is not None and value.organization_id != repeater.organization_id:
            raise serializers.ValidationError(
                "League must belong to the series' organization."
            )
        return value

    def validate(self, data: dict[str, Any]) -> dict[str, Any]:
        repeater = self.context["repeater"]
        # Same cross-field rule EventSerializer.validate and
        # EventRepeaterSerializer.validate carry; "effective" = override else series.
        game_type = data.get("game_type", repeater.game_type)
        game_mode = data.get("game_mode", repeater.game_mode)
        if game_mode in ("captains_mode", "turbo") and game_type != 1:
            raise serializers.ValidationError(
                {"game_mode": f"'{game_mode}' is only valid for Dota 2 events."}
            )
        ends_at = data.get("ends_at")
        if ends_at is not None and ends_at <= data["scheduled_at"]:
            raise serializers.ValidationError(
                {"ends_at": "End time must be after the start time."}
            )
        self.check_lobby_steam_league(data, repeater)
        # The effective mode decides: fixed needs a password (typed here or
        # the series' fixed one); random generates one, so any typed
        # password is dropped.
        overrides = data.get("overrides", {})
        mode = data.get("dota_lobby_password_mode", repeater.dota_lobby_password_mode)
        if mode == PasswordMode.FIXED:
            inherited = (
                repeater.dota_lobby_password
                if repeater.dota_lobby_password_mode == PasswordMode.FIXED
                else ""
            )
            password = _valid_fixed_password(data.get("dota_lobby_password", inherited))
            data["dota_lobby_password"] = password
            overrides["dota_lobby_password"] = password
        else:
            data.pop("dota_lobby_password", None)
            overrides.pop("dota_lobby_password", None)
        return data

    def to_internal_value(self, data: Any) -> dict[str, Any]:
        validated = super().to_internal_value(data)
        # Source overrides from the COERCED values, never the raw body:
        # tournament_league is a ForeignKey and setattr() rejects a bare pk.
        validated["overrides"] = {
            k: validated[k]
            for k in self.OVERRIDE_FIELDS
            if k in data and k in validated
        }
        if validated.get("ends_at") is not None:
            validated["overrides"]["ends_at"] = validated["ends_at"]
        return validated
