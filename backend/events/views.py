from typing import Any

from cacheops import cached_as
from django.contrib.auth.models import AnonymousUser
from django.db import transaction
from django.db.models import (
    BooleanField,
    Count,
    Exists,
    F,
    OuterRef,
    Prefetch,
    Q,
    QuerySet,
    Value,
)
from django.utils import timezone
from rest_framework import permissions, serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import NotAuthenticated, PermissionDenied
from rest_framework.request import Request
from rest_framework.response import Response

from app.cache_utils import invalidate_after_commit, invalidate_obj
from app.models import CustomUser, Organization, OrgLog
from app.permissions_org import (
    has_event_staff_access,
    has_org_admin_access,
    has_org_staff_access,
)
from events.completion import close_event
from events.constants import EventState, SignupStatus
from events.models import (
    Event,
    EventRepeater,
    EventSignup,
    EventTeam,
    OrgEventDefaults,
    RepeaterSubscription,
)
from events.serializers import (
    EventRepeaterSerializer,
    EventRepeaterSlimSerializer,
    EventSerializer,
    EventSignupSerializer,
    EventSlimSerializer,
    EventTeamSerializer,
    OrgEventDefaultsSerializer,
    RepeaterSubscriptionSerializer,
)
from events.services import (
    approve_signup,
    cancel_signup,
    confirm_signup,
    create_tournament_for_event,
    demote_to_waitlist,
    ensure_discord_event,
    ensure_tournament_with_signups,
    finalize_event_tournament,
    is_registered_for_event,
    log_lobby_password_changed,
    regenerate_event_lobby_password,
    reinstate_signup,
    reject_signup,
    resolve_or_create_org_user,
    restart_event_tournament,
    staff_add_signup,
    sync_future_events,
    sync_tournament_from_event,
    teardown_event,
    unconfirm_signup,
)
from events.utils import starts_in_future
from lobby.passwords import PasswordMode
from org.contributions.services import should_sync_staff, sync_event_staff_entries
from org.feature_errors import not_permitted
from telemetry.logging import get_logger
from user.models import BaseUserProfile
from user.querysets import with_user_profiles

logger = get_logger(__name__)


class IsOrgStaff(permissions.BasePermission):
    def has_object_permission(self, request, view, obj):
        org = getattr(obj, "organization", None)
        if org is None and hasattr(obj, "event"):
            org = obj.event.organization
        return org and has_org_staff_access(request.user, org)


def _annotate_event_qs(qs):
    """Add signup_count and confirmed_count annotations."""
    return qs.annotate(
        signup_count=Count(
            "signups",
            filter=~Q(
                signups__status__in=[
                    SignupStatus.CANCELLED,
                    SignupStatus.REJECTED,
                ]
            ),
        ),
        confirmed_count=Count(
            "signups",
            filter=Q(signups__status=SignupStatus.CONFIRMED),
        ),
    )


def with_event_staff(qs: QuerySet[Event]) -> QuerySet[Event]:
    return (
        qs.select_related("host__base_profile")
        .prefetch_related(
            Prefetch("helpers", queryset=with_user_profiles(CustomUser.objects.all()))
        )
        .nocache()
    )


def _attach_user_can_manage(
    payload: dict[str, Any] | list[dict[str, Any]], user: CustomUser | AnonymousUser
) -> dict[str, Any] | list[dict[str, Any]]:
    """Mutate a serialized Event payload (or list of them) to set user_can_manage per-request.

    Called AFTER cached_as serves a payload, so the cache itself stays user-agnostic.
    The Event instances are looked up by id from the payload; one batched query
    covers both list and single-item cases.
    """
    if not user or not user.is_authenticated:
        return payload  # default False already set by serializer
    items = payload if isinstance(payload, list) else [payload]
    if not items:
        return payload
    events_by_pk = {
        e.pk: e
        for e in Event.objects.filter(pk__in=[p["id"] for p in items]).select_related(
            "organization", "tournament_league"
        )
    }
    admin_by_org: dict[int, bool] = {}
    for p in items:
        ev = events_by_pk.get(p["id"])
        if ev is not None:
            p["user_can_manage"] = has_event_staff_access(user, ev)
            if ev.organization_id not in admin_by_org:
                admin_by_org[ev.organization_id] = has_org_admin_access(
                    user, ev.organization
                )
            p["user_can_manage_event_staff"] = admin_by_org[ev.organization_id]
    return payload


def _event_payload(event_pk: int, user: CustomUser) -> dict[str, Any]:
    qs = with_event_staff(_annotate_event_qs(Event.objects.filter(pk=event_pk)))
    data = EventSerializer(qs.first()).data
    _attach_user_can_manage(data, user)
    return data


def _require_event_staff_manager(user: CustomUser, event: Event) -> None:
    if not user.is_authenticated:
        raise NotAuthenticated()
    if not has_org_admin_access(user, event.organization):
        raise not_permitted()


class EventStaffInputSerializer(serializers.Serializer):
    host_id = serializers.IntegerField(allow_null=True)
    helper_ids = serializers.ListField(
        child=serializers.IntegerField(), allow_empty=True
    )

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        host_id: int | None = attrs["host_id"]
        helper_ids: list[int] = list(dict.fromkeys(attrs["helper_ids"]))
        if host_id is not None and host_id in helper_ids:
            raise serializers.ValidationError(
                {"helper_ids": "The host cannot also be a helper."}
            )
        wanted = set(helper_ids) | ({host_id} if host_id is not None else set())
        found = set(
            CustomUser.objects.nocache()
            .filter(pk__in=wanted)
            .values_list("pk", flat=True)
        )
        missing = sorted(wanted - found)
        if missing:
            raise serializers.ValidationError({"users": f"Unknown user ids: {missing}"})
        attrs["helper_ids"] = helper_ids
        return attrs


def _pk_or_none(pk: str | None) -> int | None:
    """The URL pk as an int; the router accepts any non-slash text."""
    try:
        return int(pk) if pk is not None else None
    except ValueError:
        return None


def _no_lobby_password() -> Response:
    # 404 rather than 403: do not reveal to outsiders that a password exists.
    return Response({"detail": "Not found."}, status=status.HTTP_404_NOT_FOUND)


def _staff_lobby_password(event: Event) -> dict:
    """The event's password settings for org staff.

    `source` is `series` while the event matches its series (an on-schedule
    event with the same mode and, when fixed, the same password): the next
    series save keeps it as it is. Otherwise `event`.
    """
    repeater = event.event_repeater
    from_series = (
        repeater is not None
        and not event.is_off_schedule
        and event.dota_lobby_password_mode == repeater.dota_lobby_password_mode
        and (
            event.dota_lobby_password_mode == PasswordMode.RANDOM
            or event.dota_lobby_password == repeater.dota_lobby_password
        )
    )
    return {
        "mode": event.dota_lobby_password_mode,
        "password": event.dota_lobby_password,
        "source": "series" if from_series else "event",
        "can_manage": True,
    }


class EventRepeaterViewSet(viewsets.ModelViewSet):
    serializer_class = EventRepeaterSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_serializer_class(self):
        if self.action == "list":
            return EventRepeaterSlimSerializer
        return EventRepeaterSerializer

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if self.action in ("update", "partial_update", "destroy"):
            if not has_org_staff_access(request.user, obj.organization):
                self.permission_denied(request)

    def perform_destroy(self, instance):
        """Tear down the series' still-active occurrences (and their live Discord
        scheduled events) before deleting the series, so sync_discord_events can't
        resurrect them as ghosts. Terminal (completed/cancelled) occurrences are
        left as orphans via Event.event_repeater=SET_NULL for historical record.
        """
        active_states = [
            EventState.UPCOMING,
            EventState.SIGNUPS_OPEN,
            EventState.ROLL_CALL,
        ]
        for event in list(instance.events.filter(state__in=active_states)):
            teardown_event(event)
        instance.delete()

    def get_queryset(self):
        from django.db.models import Min

        qs = EventRepeater.objects.select_related(
            "organization", "tournament_league", "created_by"
        ).annotate(
            subscriber_count=Count("subscriptions"),
            next_event_date=Min(
                "events__scheduled_at",
                filter=Q(
                    events__state__in=[EventState.UPCOMING, EventState.SIGNUPS_OPEN]
                ),
            ),
        )
        if self.request.user.is_authenticated:
            qs = qs.annotate(
                is_subscribed=Exists(
                    RepeaterSubscription.objects.filter(
                        event_repeater=OuterRef("pk"),
                        user=self.request.user,
                    )
                )
            )
        else:
            qs = qs.annotate(is_subscribed=Value(False, output_field=BooleanField()))
        org_id = self.request.query_params.get("organization")
        if org_id:
            qs = qs.filter(organization_id=org_id)
        is_active = self.request.query_params.get("is_active")
        if is_active == "true":
            qs = qs.filter(is_active=True)
        elif is_active == "false":
            qs = qs.filter(is_active=False)
        return qs

    def list(self, request, *args, **kwargs):
        cache_key = f"repeater_list:{request.get_full_path()}"

        @cached_as(EventRepeater, Event, extra=cache_key, timeout=60 * 60)
        def get_data():
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return serializer.data

        return Response(get_data())

    def retrieve(self, request, *args, **kwargs):
        pk = kwargs.get("pk")
        cache_key = f"repeater_detail:{pk}"

        @cached_as(
            EventRepeater.objects.filter(pk=pk),
            keep_fresh=True,
            extra=cache_key,
            timeout=60 * 60,
        )
        def get_data():
            instance = self.get_object()
            return self.get_serializer(instance).data

        return Response(get_data())

    def perform_create(self, serializer):
        from app.cache_utils import invalidate_after_commit

        org = serializer.validated_data.get("organization")
        if not has_org_staff_access(self.request.user, org):
            raise PermissionDenied("You do not have staff access to this organization.")
        repeater = serializer.save(created_by=self.request.user)
        invalidate_after_commit(repeater)

    def perform_update(self, serializer):
        from app.cache_utils import invalidate_after_commit

        # Snapshot schedule fields before save so we can detect a change
        # and tell sync_future_events to realign occurrences. Without this,
        # editing day_of_week leaves stale UPCOMING rows on the old day
        # while generate_events_for_repeater creates new rows on the new
        # day — admins see duplicates. is_active is in the tuple so a plain
        # PATCH that unpauses a series realigns exactly like the reactivate
        # button does.
        schedule_fields = (
            "day_of_week",
            "time_of_day",
            "timezone",
            "starts_at",
            "frequency",
            "is_active",
        )
        before = {f: getattr(serializer.instance, f) for f in schedule_fields}
        repeater = serializer.save()
        schedule_changed = any(
            before[f] != getattr(repeater, f) for f in schedule_fields
        )
        future_events = sync_future_events(repeater, realign_schedule=schedule_changed)
        # Single batched invalidation — repeater + every cascaded child
        invalidate_after_commit(repeater, *future_events)

    @action(
        detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated]
    )
    def subscribe(self, request, pk=None):
        """Subscribe to event notifications for this repeater.
        Any authenticated user can subscribe (not limited to org staff).
        """
        repeater = self.get_object()
        _, created = RepeaterSubscription.objects.get_or_create(
            event_repeater=repeater, user=request.user
        )
        if created:
            invalidate_obj(repeater)
            return Response({"detail": "Subscribed"}, status=status.HTTP_201_CREATED)
        return Response({"detail": "Already subscribed"}, status=status.HTTP_200_OK)

    @action(detail=True, methods=["get"])
    def subscribers(self, request, pk=None):
        """List all subscribers for this repeater."""
        repeater = self.get_object()
        # RepeaterSubscriptionSerializer reads user.nickname + user.avatar,
        # which go through the @property on CustomUser → base_profile (T1
        # epic). Without this prefetch the list view is N+1 cold-cache.
        subs = with_user_profiles(
            RepeaterSubscription.objects.filter(event_repeater=repeater), "user"
        )
        return Response(RepeaterSubscriptionSerializer(subs, many=True).data)

    @action(
        detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated]
    )
    def unsubscribe(self, request, pk=None):
        """Unsubscribe from event notifications for this repeater."""
        repeater = self.get_object()
        deleted, _ = RepeaterSubscription.objects.filter(
            event_repeater=repeater, user=request.user
        ).delete()
        if deleted:
            invalidate_obj(repeater)
        return Response({"detail": "Unsubscribed"}, status=status.HTTP_200_OK)

    @action(
        detail=True,
        methods=["post"],
        url_path="create-event",
        permission_classes=[permissions.IsAuthenticated],
    )
    def create_event(self, request, pk=None):
        """Create a single off-schedule ("one-off") event from this series."""
        from app.cache_utils import invalidate_after_commit
        from events.serializers import OneOffEventCreateSerializer
        from events.services import OccurrenceCollision, create_off_schedule_event

        repeater = self.get_object()
        if not has_org_staff_access(request.user, repeater.organization):
            return Response(
                {"detail": "You do not have staff access to this organization."},
                status=status.HTTP_403_FORBIDDEN,
            )

        serializer = OneOffEventCreateSerializer(
            data=request.data, context={"repeater": repeater, "request": request}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        try:
            event = create_off_schedule_event(
                repeater,
                scheduled_at=data["scheduled_at"],
                created_by=request.user,
                overrides=data.get("overrides") or {},
            )
        except OccurrenceCollision as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        if data.get("open_signups"):
            try:
                event.transition_state(EventState.SIGNUPS_OPEN)
            except ValueError:
                pass

        invalidate_after_commit(repeater, event)
        logger.info(
            "off_schedule_event_endpoint",
            system="events",
            subsystem="views",
            repeater_id=repeater.pk,
            event_id=event.pk,
        )
        return Response(
            EventSerializer(event, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(
        detail=True,
        methods=["get"],
        url_path="lobby-password",
        permission_classes=[permissions.IsAuthenticated],
    )
    def lobby_password(self, request, pk=None):
        """The series' lobby password mode and fixed password (org staff only).

        Never cached. Writes go through the series PATCH (write-only field).
        """
        repeater = EventRepeater.objects.nocache().filter(pk=_pk_or_none(pk)).first()
        if repeater is None or not has_org_staff_access(
            request.user, repeater.organization
        ):
            return _no_lobby_password()
        fixed = repeater.dota_lobby_password_mode == PasswordMode.FIXED
        return Response(
            {
                "mode": repeater.dota_lobby_password_mode,
                "password": repeater.dota_lobby_password if fixed else None,
                "can_manage": True,
            }
        )

    @action(
        detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated]
    )
    def reactivate(self, request, pk=None):
        """Reactivate a paused series and realign its upcoming events."""
        from app.cache_utils import invalidate_after_commit

        repeater = self.get_object()
        if not has_org_staff_access(request.user, repeater.organization):
            return Response(
                {"detail": "You do not have staff access to this organization."},
                status=status.HTTP_403_FORBIDDEN,
            )

        before = set(
            Event.objects.filter(event_repeater=repeater).values_list("pk", flat=True)
        )
        if not repeater.is_active:
            repeater.is_active = True
            repeater.save(update_fields=["is_active", "updated_at"])

        # realign_schedule=True, not the bare generator: a schedule edit made
        # while paused would otherwise leave stale rows alongside new ones.
        touched = sync_future_events(repeater, realign_schedule=True)
        after = set(
            Event.objects.filter(event_repeater=repeater).values_list("pk", flat=True)
        )
        created_count = len(after - before)

        if created_count:
            detail = f"Series reactivated. {created_count} upcoming event(s) created."
        elif repeater.ends_at and repeater.ends_at < timezone.localdate():
            detail = (
                "Series reactivated, but no events were created because its "
                "end date has passed."
            )
        else:
            detail = "Series reactivated. No new events were due."

        invalidate_after_commit(repeater, *touched)
        logger.info(
            "repeater_reactivated",
            system="events",
            subsystem="views",
            repeater_id=repeater.pk,
            created_count=created_count,
        )
        return Response(
            {"detail": detail, "created_count": created_count, "is_active": True},
            status=status.HTTP_200_OK,
        )


class EventViewSet(viewsets.ModelViewSet):
    serializer_class = EventSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get_serializer_class(self):
        if self.action == "list":
            return EventSlimSerializer
        return EventSerializer

    def get_queryset(self):
        from django.db.models.functions import Abs, Now

        qs = _annotate_event_qs(
            Event.objects.select_related(
                "organization", "tournament_league", "created_by", "tournament"
            )
        )
        if self.action != "list":
            qs = with_event_staff(qs)
        params = self.request.query_params

        # Filter by organization
        org_id = params.get("organization")
        if org_id:
            qs = qs.filter(organization_id=org_id)

        # Filter by state (single or comma-separated)
        state = params.get("state")
        states = params.get("states")
        if states:
            qs = qs.filter(state__in=states.split(","))
        elif state:
            qs = qs.filter(state=state)

        # Search by name or organization name
        search = params.get("search")
        if search:
            qs = qs.filter(
                Q(name__icontains=search) | Q(organization__name__icontains=search)
            )

        # Filter by event repeater
        repeater_id = params.get("event_repeater")
        if repeater_id:
            qs = qs.filter(event_repeater_id=repeater_id)

        # Date range filters (ISO format)
        scheduled_before = params.get("scheduled_before")
        if scheduled_before:
            qs = qs.filter(scheduled_at__lt=scheduled_before)
        scheduled_after = params.get("scheduled_after")
        if scheduled_after:
            qs = qs.filter(scheduled_at__gte=scheduled_after)

        # Filter by signups_open_at (for open_scheduled_signups task)
        signups_due_before = params.get("signups_due_before")
        if signups_due_before:
            qs = qs.filter(
                signups_open_at__isnull=False, signups_open_at__lte=signups_due_before
            )

        # Boolean filters
        has_repeater = params.get("has_repeater")
        if has_repeater == "true":
            qs = qs.filter(event_repeater__isnull=False)

        has_announcement_channel = params.get("has_announcement_channel")
        if has_announcement_channel == "true":
            qs = qs.filter(discord_announcement_channel_id__gt="")

        # Ordering
        ordering = params.get("ordering", "-scheduled_at")
        if ordering == "closest":
            qs = qs.annotate(distance=Abs(F("scheduled_at") - Now())).order_by(
                "distance"
            )
        elif ordering in (
            "scheduled_at",
            "-scheduled_at",
            "name",
            "-signup_count",
        ):
            qs = qs.order_by(ordering)

        return qs

    def list(self, request, *args, **kwargs):
        cache_key = f"event_list:{request.get_full_path()}"

        @cached_as(Event, EventSignup, extra=cache_key, timeout=60 * 60)
        def get_data():
            queryset = self.filter_queryset(self.get_queryset())
            serializer = self.get_serializer(queryset, many=True)
            return serializer.data

        # cacheops returns a fresh deserialization on every hit; safe to mutate in place.
        data = list(get_data())  # shallow-copy the outer container
        _attach_user_can_manage(data, request.user)
        return Response(data)

    def retrieve(self, request, *args, **kwargs):
        pk = kwargs.get("pk")
        cache_key = f"event_detail:{pk}"

        @cached_as(
            Event.objects.filter(pk=pk),
            EventSignup,
            CustomUser,
            BaseUserProfile,
            keep_fresh=True,
            extra=cache_key,
            timeout=60 * 60,
        )
        def get_data():
            instance = self.get_object()
            return self.get_serializer(instance).data

        data = dict(get_data())  # shallow-copy
        _attach_user_can_manage(data, request.user)
        return Response(data)

    def perform_create(self, serializer):
        org = serializer.validated_data.get("organization")
        if not has_org_staff_access(self.request.user, org):
            raise PermissionDenied(
                "You do not have permission to create events for this organization."
            )
        from app.cache_utils import invalidate_after_commit

        event = serializer.save(created_by=self.request.user)
        create_tournament_for_event(event)
        # Auto-create DiscordEvent if org has Discord configured
        ensure_discord_event(event)
        # Auto-open signups if requested via query param
        if self.request.query_params.get("open_signups") == "true":
            try:
                event.transition_state(EventState.SIGNUPS_OPEN)
            except ValueError:
                pass  # Event already in a non-upcoming state
        invalidate_after_commit(event)
        from events.discord import notify_create_discord_event

        notify_create_discord_event(event)

    def perform_update(self, serializer: EventSerializer) -> None:
        from app.cache_utils import invalidate_after_commit

        previous_password = serializer.instance.dota_lobby_password
        previous_ledger_fields = (
            serializer.instance.scheduled_at,
            serializer.instance.ends_at,
            serializer.instance.name,
        )
        event = serializer.save()
        invalidate_after_commit(event)
        if (
            event.scheduled_at,
            event.ends_at,
            event.name,
        ) != previous_ledger_fields and should_sync_staff(event):
            sync_event_staff_entries(event)
        if event.dota_lobby_password != previous_password:
            log_lobby_password_changed(event, "event_update")
        result = sync_tournament_from_event(event)
        self._cascade_warning = result.get("warning")

        # If Discord config is set but no announcement has been sent yet, send it now.
        # This handles the case where an admin edits an event to add Discord config.
        # Only send when signups are open — not for upcoming events.
        if (
            event.state == EventState.SIGNUPS_OPEN
            and event.discord_announcement
            and event.discord_announcement_channel_id
        ):
            from discordbot.models import DiscordEvent

            try:
                discord_event = event.discord_event
                has_announcement = (
                    discord_event.signup_message
                    and discord_event.signup_message.has_posted
                )
            except DiscordEvent.DoesNotExist:
                has_announcement = False

            # Fall back to DiscordMessageLog for pre-migration events
            if not has_announcement:
                from discordbot.models import DiscordMessageLog

                has_announcement = DiscordMessageLog.objects.filter(
                    source="event_announcement", source_id=event.pk, success=True
                ).exists()

            if not has_announcement:
                from events.discord import notify_create_discord_event

                notify_create_discord_event(event)

    def update(self, request, *args, **kwargs):
        response = super().update(request, *args, **kwargs)
        if hasattr(self, "_cascade_warning") and self._cascade_warning:
            response.data["_warning"] = self._cascade_warning
        return response

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        # Only enforce staff check for standard CRUD mutations (update/delete).
        # Custom actions (rsvp, open_signups, etc.) handle permissions internally.
        if self.action in ("update", "partial_update", "destroy"):
            if not has_org_staff_access(request.user, obj.organization):
                self.permission_denied(request)

    @action(
        detail=True,
        methods=["get"],
        url_path="lobby-password",
        permission_classes=[permissions.AllowAny],
    )
    def lobby_password(self, request, pk=None):
        """The event's lobby password, for org staff and registered players.

        Staff (who may edit the event) also get the mode and where the
        password comes from; registered players (events.services.
        is_registered_for_event) get the password only; anyone else a 404.
        Never cached: the answer depends on the user.
        """
        event = (
            Event.objects.nocache()
            .select_related("organization", "event_repeater")
            .filter(pk=_pk_or_none(pk))
            .first()
        )
        if event is None:
            return _no_lobby_password()
        if has_org_staff_access(request.user, event.organization):
            return Response(_staff_lobby_password(event))
        if is_registered_for_event(request.user, event):
            return Response({"password": event.dota_lobby_password})
        return _no_lobby_password()

    @action(
        detail=True,
        methods=["post"],
        url_path="lobby-password/regenerate",
        permission_classes=[permissions.IsAuthenticated],
    )
    def regenerate_lobby_password(self, request, pk=None):
        """Generate a new random lobby password (org staff, random mode only).

        Lobbies that already exist keep their password.
        """
        event = (
            Event.objects.nocache()
            .select_related("organization", "tournament", "event_repeater")
            .filter(pk=_pk_or_none(pk))
            .first()
        )
        if event is None or not has_org_staff_access(request.user, event.organization):
            return _no_lobby_password()
        try:
            regenerate_event_lobby_password(event)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)
        return Response(_staff_lobby_password(event))

    @action(
        detail=True,
        methods=["post"],
        permission_classes=[permissions.IsAuthenticated],
    )
    def signup(self, request, pk=None):
        """Single canonical signup endpoint accepting an intent + optional profile patch.

        Body: {"intent": "rsvp" | "tentative", "profile": {...}}
        Replaces the older /rsvp/ and /tentative/ actions (deleted in Task 29).
        """
        from django.core.exceptions import ValidationError as DjangoValidationError
        from django.db import transaction
        from pydantic import ValidationError as PydanticValidationError

        from events.schemas import SignupInputPatch
        from events.services import (
            apply_signup_input,
            create_tentative_signup,
            process_rsvp,
            resolve_or_create_org_user,
        )

        event = self.get_object()
        if event.state != EventState.SIGNUPS_OPEN:
            return Response(
                {"error": "Event is not accepting signups"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        body = request.data or {}
        intent = body.get("intent")
        if intent not in ("rsvp", "tentative"):
            return Response(
                {"error": "intent must be 'rsvp' or 'tentative'"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            patch = SignupInputPatch(**(body.get("profile") or {}))
        except PydanticValidationError as exc:
            first = exc.errors()[0] if exc.errors() else {}
            msg = first.get("msg") or str(exc)
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)

        org_user = resolve_or_create_org_user(request.user, event.organization)

        try:
            with transaction.atomic():
                apply_signup_input(org_user=org_user, event=event, patch=patch)
                if intent == "rsvp":
                    signup = process_rsvp(event, request.user)
                else:
                    signup = create_tentative_signup(event, request.user)
        except DjangoValidationError as exc:
            msg = exc.messages[0] if hasattr(exc, "messages") else str(exc)
            return Response({"error": msg}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            EventSignupSerializer(signup, context={"request": request}).data,
            status=status.HTTP_201_CREATED,
        )

    @action(detail=True, methods=["post"], url_path="admin-signup")
    def admin_signup(self, request, pk=None):
        """Admin adds a user to the event signup list.
        POST /api/events/<pk>/admin-signup/ {"user_id": <pk>}
        """
        from app.models import CustomUser

        event = self.get_object()
        if not has_event_staff_access(request.user, event):
            return Response(status=status.HTTP_403_FORBIDDEN)
        user_id = request.data.get("user_id")
        if not user_id:
            return Response(
                {"error": "user_id is required"}, status=status.HTTP_400_BAD_REQUEST
            )
        try:
            user = CustomUser.objects.get(pk=user_id)
        except CustomUser.DoesNotExist:
            return Response(
                {"error": "User not found"}, status=status.HTTP_404_NOT_FOUND
            )
        try:
            signup = staff_add_signup(event, user)
            return Response(
                EventSignupSerializer(signup, context={"request": request}).data,
                status=status.HTTP_201_CREATED,
            )
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def open_signups(self, request, pk=None):
        event = self.get_object()
        if not has_event_staff_access(request.user, event):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            event.transition_state(EventState.SIGNUPS_OPEN)
            qs = with_event_staff(_annotate_event_qs(Event.objects.filter(pk=event.pk)))
            data = EventSerializer(qs.first()).data
            _attach_user_can_manage(data, request.user)
            return Response(data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def start_roll_call(self, request, pk=None):
        event = self.get_object()
        if not has_event_staff_access(request.user, event):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            event.transition_state(EventState.ROLL_CALL)
            qs = with_event_staff(_annotate_event_qs(Event.objects.filter(pk=event.pk)))
            data = EventSerializer(qs.first()).data
            _attach_user_can_manage(data, request.user)
            return Response(data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def reopen_signups(self, request, pk=None):
        """Corrective transition from ROLL_CALL back to SIGNUPS_OPEN.

        Quiet: no Discord re-announcement, no signup-changed notify. Existing
        confirmations and tournament additions are preserved.
        """
        from app.cache_utils import invalidate_after_commit

        event = self.get_object()
        if not has_event_staff_access(request.user, event):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            with transaction.atomic():
                event.transition_state(EventState.SIGNUPS_OPEN)
                invalidate_after_commit(event)
            qs = with_event_staff(_annotate_event_qs(Event.objects.filter(pk=event.pk)))
            data = EventSerializer(qs.first()).data
            _attach_user_can_manage(data, request.user)
            return Response(data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def start_tournament(self, request, pk=None):
        """Start the tournament (after roll call or directly).

        Self-heals legacy events whose tournament is missing or empty (#200).
        """
        event = self.get_object()
        if not has_event_staff_access(request.user, event):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            if event.state not in (EventState.ROLL_CALL, EventState.SIGNUPS_OPEN):
                return Response(
                    {"error": f"Cannot start tournament from '{event.state}' state."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            ensure_tournament_with_signups(event)
            event.transition_state(EventState.IN_PROGRESS)
            finalize_event_tournament(event)
            # Start auto-create herodrafts polling if enabled
            if event.tournament and event.tournament.auto_create_hero_drafts:
                from events.discord.tournament_dispatch import (
                    start_auto_create_herodrafts,
                )

                start_auto_create_herodrafts(event.tournament)
            qs = with_event_staff(_annotate_event_qs(Event.objects.filter(pk=event.pk)))
            data = EventSerializer(qs.first()).data
            _attach_user_can_manage(data, request.user)
            return Response(data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def perform_destroy(self, instance):
        """Clean up tournament and Discord messages before deleting event."""
        teardown_event(instance)

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        event = self.get_object()
        if not has_event_staff_access(request.user, event):
            return Response(status=status.HTTP_403_FORBIDDEN)
        # Function-local: events.tasks imports events.services, which imports this module.
        from discordbot.models import DiscordEvent
        from events.tasks import delete_discord_scheduled_event

        try:
            with transaction.atomic():
                # Delete linked tournament before cancelling
                if event.tournament:
                    tournament = event.tournament
                    event.tournament = None
                    event.save(update_fields=["tournament", "updated_at"])
                    tournament.delete()
                event.transition_state(EventState.CANCELLED)
                try:
                    discord_event = event.discord_event
                except DiscordEvent.DoesNotExist:
                    discord_event = None
                if discord_event is not None and discord_event.scheduled_event_id:
                    # Clearing the id stops the 60s sync_discord_events resurrecting it.
                    delete_discord_scheduled_event.delay(
                        discord_event.guild_id, discord_event.scheduled_event_id
                    )
                    discord_event.scheduled_event_id = None
                    discord_event.save(update_fields=["scheduled_event_id"])
                    logger.info(
                        "event_cancel_discord_scheduled_event_deleted",
                        system="events",
                        subsystem="views",
                        event_id=event.pk,
                        guild_id=discord_event.guild_id,
                    )
            qs = with_event_staff(_annotate_event_qs(Event.objects.filter(pk=event.pk)))
            data = EventSerializer(qs.first()).data
            _attach_user_can_manage(data, request.user)
            return Response(data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def complete(self, request: Request, pk: str | None = None) -> Response:
        event = self.get_object()
        _require_event_staff_manager(request.user, event)
        if event.state not in (EventState.ROLL_CALL, EventState.IN_PROGRESS):
            return Response(
                {"error": f"Cannot complete an event in '{event.state}' state."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        result = close_event(
            event, new_state=EventState.COMPLETED, source="admin", actor=request.user
        )
        if not result.closed:
            return Response(
                {"error": f"Cannot complete an event in '{result.state}' state."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(_event_payload(event.pk, request.user))

    @action(detail=True, methods=["put"], url_path="staff")
    def staff(self, request: Request, pk: str | None = None) -> Response:
        event = self.get_object()
        _require_event_staff_manager(request.user, event)
        body = EventStaffInputSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        host_id: int | None = body.validated_data["host_id"]
        helper_ids: list[int] = body.validated_data["helper_ids"]
        org = event.organization
        with transaction.atomic():
            users = CustomUser.objects.nocache().in_bulk(
                [*helper_ids, *([host_id] if host_id is not None else [])]
            )
            for user in users.values():
                resolve_or_create_org_user(user, org)
            previous_host_id = event.host_id
            previous_helper_ids = sorted(
                event.helpers.nocache().values_list("pk", flat=True)
            )
            event.host_id = host_id
            event.save(update_fields=["host", "updated_at"])
            event.helpers.set(helper_ids)
            synced = should_sync_staff(event)
            if synced:
                sync_event_staff_entries(event)
            OrgLog.objects.create(
                organization=org,
                actor=request.user,
                action="set_event_staff",
                details={
                    "event_id": event.pk,
                    "host_id": host_id,
                    "helper_ids": helper_ids,
                    "previous_host_id": previous_host_id,
                    "previous_helper_ids": previous_helper_ids,
                },
            )
            invalidate_after_commit(event)
        logger.info(
            "event_staff_set",
            system="events",
            subsystem="views",
            event_id=event.pk,
            org_id=org.pk,
            actor_id=request.user.pk,
            host_id=host_id,
            helper_count=len(helper_ids),
            synced=synced,
        )
        return Response(_event_payload(event.pk, request.user))

    @action(detail=True, methods=["get"])
    def discord(self, request, pk=None):
        """Get Discord state for this event.
        GET /api/events/<pk>/discord/
        """
        event = self.get_object()

        from discordbot.models import DiscordEvent

        try:
            discord_event = event.discord_event
        except DiscordEvent.DoesNotExist:
            return Response({"detail": "No Discord state for this event"}, status=404)

        from cacheops import cached_as

        from discordbot.models import DiscordEventDM, DiscordEventLog, DiscordMessageLog
        from discordbot.serializers_discord_event import DiscordEventDetailSerializer

        @cached_as(
            DiscordEvent,
            DiscordEventLog,
            DiscordEventDM,
            DiscordMessageLog,
            extra=f"discord_state:{pk}",
            timeout=60,
        )
        def get_data():
            return DiscordEventDetailSerializer(discord_event).data

        return Response(get_data())

    @action(detail=True, methods=["post"])
    def restart_tournament(self, request, pk=None):
        """Delete current tournament, create fresh one, reopen signups."""
        event = self.get_object()
        if not has_event_staff_access(request.user, event):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            restart_event_tournament(event)
            event.refresh_from_db()
            qs = with_event_staff(_annotate_event_qs(Event.objects.filter(pk=event.pk)))
            data = EventSerializer(qs.first()).data
            _attach_user_can_manage(data, request.user)
            return Response(data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class EventSignupViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EventSignupSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        # EventSignupSerializer ships user.nickname (as `username`) +
        # user.avatar — both resolve through the CustomUser @property to
        # base_profile (T1 epic). Without user__base_profile this is N+1
        # cold-cache on busy events.
        qs = with_user_profiles(
            EventSignup.objects.select_related("event", "event_team"), "user"
        )
        event_id = self.request.query_params.get("event")
        if event_id:
            qs = qs.filter(event_id=event_id)
        return qs

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        signup = self.get_object()
        if not has_event_staff_access(request.user, signup.event):
            return Response(status=status.HTTP_403_FORBIDDEN)

        # Optional MMR override from admin
        mmr_override = None
        if request.data:
            raw_mmr = request.data.get("mmr")
            if raw_mmr is not None:
                try:
                    mmr_override = int(raw_mmr)
                except (TypeError, ValueError):
                    return Response(
                        {"error": "mmr must be an integer."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
                if not (0 <= mmr_override <= 20000):
                    return Response(
                        {"error": "mmr must be between 0 and 20000."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )

        try:
            result = approve_signup(signup, mmr_override=mmr_override)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        # Audit log for MMR override
        if mmr_override is not None:
            from app.models import OrgLog

            OrgLog.objects.create(
                organization=signup.event.organization,
                actor=request.user,
                action="set_mmr",
                target_user=signup.user,
                details={"mmr": mmr_override, "event_id": signup.event.pk},
            )

        return Response(
            EventSignupSerializer(result, context={"request": request}).data
        )

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        signup = self.get_object()
        if not has_event_staff_access(request.user, signup.event):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            return Response(
                EventSignupSerializer(
                    reject_signup(signup), context={"request": request}
                ).data
            )
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        signup = self.get_object()
        if not has_event_staff_access(request.user, signup.event):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            return Response(
                EventSignupSerializer(
                    confirm_signup(signup), context={"request": request}
                ).data
            )
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def cancel_signup(self, request, pk=None):
        signup = self.get_object()
        if signup.user != request.user and not has_event_staff_access(
            request.user, signup.event
        ):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            return Response(
                EventSignupSerializer(
                    cancel_signup(signup), context={"request": request}
                ).data
            )
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def unconfirm(self, request, pk=None):
        """Revert a confirmed signup back to approved."""
        signup = self.get_object()
        if not has_event_staff_access(request.user, signup.event):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            return Response(
                EventSignupSerializer(
                    unconfirm_signup(signup), context={"request": request}
                ).data
            )
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def demote(self, request, pk=None):
        """Move an active signup to the end of the waitlist."""
        signup = self.get_object()
        if not has_event_staff_access(request.user, signup.event):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            return Response(
                EventSignupSerializer(
                    demote_to_waitlist(signup), context={"request": request}
                ).data
            )
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def reinstate(self, request, pk=None):
        """Reinstate a cancelled signup (user can reinstate their own)."""
        signup = self.get_object()
        if signup.user != request.user and not has_event_staff_access(
            request.user, signup.event
        ):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            return Response(
                EventSignupSerializer(
                    reinstate_signup(signup), context={"request": request}
                ).data
            )
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class EventTeamViewSet(viewsets.ModelViewSet):
    serializer_class = EventTeamSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if self.action in ("update", "partial_update", "destroy"):
            if not has_org_staff_access(request.user, obj.event.organization):
                self.permission_denied(request)

    def get_queryset(self):
        qs = EventTeam.objects.select_related("event", "captain").annotate(
            member_count=Count("members"),
        )
        event_id = self.request.query_params.get("event")
        if event_id:
            qs = qs.filter(event_id=event_id)
        return qs

    def perform_create(self, serializer):
        event = serializer.validated_data.get("event")
        if not has_org_staff_access(self.request.user, event.organization):
            raise PermissionDenied(
                "You do not have permission to create teams for this event."
            )
        serializer.save()


class OrgEventDefaultsViewSet(viewsets.GenericViewSet):
    """Get or update event defaults for an organization.

    GET   /events/defaults/?organization=<pk>  — returns defaults (auto-creates if missing)
    PATCH /events/defaults/<pk>/               — update defaults (org staff only)
    """

    serializer_class = OrgEventDefaultsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return OrgEventDefaults.objects.select_related("organization")

    def list(self, request):
        org_id = request.query_params.get("organization")
        if not org_id:
            return Response(
                {"error": "organization param required"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            org = Organization.objects.get(pk=int(org_id))
        except Organization.DoesNotExist:
            return Response(
                {"error": "Organization not found"},
                status=status.HTTP_404_NOT_FOUND,
            )
        defaults, _ = OrgEventDefaults.objects.get_or_create(organization=org)
        return Response(OrgEventDefaultsSerializer(defaults).data)

    def partial_update(self, request, pk=None):
        defaults = self.get_object()
        if not has_org_staff_access(request.user, defaults.organization):
            raise PermissionDenied("Staff access required.")
        serializer = self.get_serializer(defaults, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        invalidate_obj(defaults)
        return Response(serializer.data)


# ---------------------------------------------------------------------------
# Task Schedule — per-event projected timeline
# ---------------------------------------------------------------------------

from datetime import timedelta

from django.utils import timezone as tz
from rest_framework.decorators import api_view, permission_classes


@api_view(["GET"])
@permission_classes([permissions.IsAuthenticated])
def get_event_task_schedule(request, event_id):
    """Return projected task timeline for an event.

    Calculates when each notification/task will fire based on the event's
    Discord config, scheduled_at, and signups_open_at times. Checks
    DiscordMessageLog and DiscordEventLog to determine fired status.
    """
    from discordbot.models import DiscordEventLog, DiscordMessageLog

    try:
        event = Event.objects.select_related(
            "organization", "event_repeater", "tournament"
        ).get(pk=event_id)
    except Event.DoesNotExist:
        return Response({"error": "Event not found"}, status=status.HTTP_404_NOT_FOUND)

    now = tz.now()

    # Check which log sources have already fired
    fired_sources = set(
        DiscordMessageLog.objects.filter(
            source_id=event.pk,
            success=True,
        ).values_list("source", flat=True)
    )

    fired_actions = set()
    try:
        discord_event = event.discord_event
        fired_actions = set(
            DiscordEventLog.objects.filter(
                discord_event=discord_event,
                success=True,
            ).values_list("action", flat=True)
        )
    except Exception:
        pass

    # Check subscriber DMs
    has_dms = False
    try:
        from discordbot.models import DiscordEventDM, DMType

        has_dms = DiscordEventDM.objects.filter(
            discord_event__event=event,
            dm_type=DMType.SIGNUP_REMINDER,
        ).exists()
    except Exception:
        pass

    # Last fired timestamps + fired_by from logs
    last_fired_map = {}
    for row in (
        DiscordMessageLog.objects.filter(source_id=event.pk, success=True)
        .select_related("fired_by")
        .order_by("-created_at")
    ):
        if row.source not in last_fired_map:
            fired_by_data = None
            if row.fired_by:
                fired_by_data = {
                    "pk": row.fired_by.pk,
                    "username": row.fired_by.username,
                    "nickname": row.fired_by.nickname,
                    "discordId": row.fired_by.discordId,
                    "avatar": row.fired_by.avatar,
                }
            last_fired_map[row.source] = {
                "created_at": row.created_at,
                "fired_by": fired_by_data,
            }

    def _task(
        task,
        label,
        enabled,
        fires_at=None,
        log_source=None,
        misconfigured=False,
        check_interval=None,
        description="",
    ):
        """Build a task entry with status and timing details."""
        entry = {
            "task": task,
            "label": label,
            "fires_at": fires_at.isoformat() if fires_at else None,
            "description": description,
            "check_interval": check_interval,
            "last_fired_at": None,
            "fired_by": None,
            "can_fire": False,
        }

        if misconfigured:
            entry["status"] = "misconfigured"
            entry["description"] = (
                description or "Enabled but missing channel/server config"
            )
            return entry
        if not enabled:
            entry["status"] = "disabled"
            return entry

        # Determine status
        if task == "signup_reminder":
            s = (
                "fired"
                if has_dms
                else ("pending" if fires_at and now < fires_at else "ready")
            )
        elif log_source and log_source in fired_sources:
            s = "fired"
        elif task == "scheduled_event" and "create_scheduled_event" in fired_actions:
            s = "fired"
        elif task == "signup_post" and "send_signup_post" in fired_actions:
            s = "fired"
        elif task == "announcement" and "event_announcement" in fired_sources:
            s = "fired"
        elif fires_at and now < fires_at:
            s = "pending"
        else:
            s = "ready"

        # Discord rejects scheduled events that start in the past, and both the
        # sync and the task skip them, so an unfired one can never fire now.
        if (
            task == "scheduled_event"
            and s == "ready"
            and not starts_in_future(event.scheduled_at, now)
        ):
            s = "disabled"
            entry["description"] = "Start time has passed; Discord rejects past starts"

        entry["status"] = s
        # signup_post + announcement support re-firing as "Repost" when the
        # Discord post is missing (deleted externally) or to push a fresh
        # version. fire_event_task clears dedup state before re-running.
        repostable = task in ("signup_post", "announcement")
        entry["can_fire"] = s in ("ready", "pending") or (s == "fired" and repostable)
        if log_source and log_source in last_fired_map:
            info = last_fired_map[log_source]
            entry["last_fired_at"] = info["created_at"].isoformat()
            entry["fired_by"] = info["fired_by"]

        return entry

    has_channel = bool(event.discord_announcement_channel_id)

    tasks = [
        _task(
            "announcement",
            "Discord Announcement",
            enabled=event.discord_announcement and has_channel,
            log_source="event_announcement",
            misconfigured=event.discord_announcement and not has_channel,
            check_interval="On signups open",
            description="Posts signup embed + buttons when signups open",
        ),
        _task(
            "signup_post",
            "Signup Post",
            enabled=event.discord_post_signups
            and bool(event.discord_post_signups_channel_id),
            misconfigured=event.discord_post_signups
            and not event.discord_post_signups_channel_id,
            check_interval="On signups open",
            description="Creates forum thread or message for signups",
        ),
        _task(
            "scheduled_event",
            "Discord Scheduled Event",
            enabled=event.discord_create_event
            and bool(event.organization.discord_server_id),
            misconfigured=event.discord_create_event
            and not event.organization.discord_server_id,
            check_interval="Every 60s (sync)",
            description="Creates a Discord guild scheduled event",
        ),
        _task(
            "signup_reminder",
            "Signup Reminder",
            enabled=event.discord_signup_reminder
            and event.event_repeater_id is not None,
            fires_at=(
                event.scheduled_at
                - timedelta(hours=event.discord_signup_reminder_hours)
                if event.discord_signup_reminder
                else None
            ),
            log_source="signup_reminder",
            check_interval="Every 30s",
            misconfigured=event.discord_signup_reminder
            and event.event_repeater_id is None,
            description=f"DMs subscribers who haven't signed up {event.discord_signup_reminder_hours}h before event",
        ),
        _task(
            "confirm_attendance",
            "Attendance Reminder",
            enabled=event.discord_confirm_attendance and has_channel,
            fires_at=(
                event.scheduled_at
                - timedelta(hours=event.discord_confirm_attendance_hours)
                if event.discord_confirm_attendance
                else None
            ),
            log_source="attendance_reminder",
            check_interval="Every 30s",
            description=f"Posts {event.discord_confirm_attendance_hours}h before event",
        ),
        _task(
            "profile_reminder",
            "Profile Reminder",
            enabled=event.discord_profile_reminder and has_channel,
            fires_at=(
                event.scheduled_at
                - timedelta(hours=event.discord_profile_reminder_hours)
                if event.discord_profile_reminder
                else None
            ),
            log_source="profile_reminder",
            check_interval="Every 30s",
            description=f"Posts {event.discord_profile_reminder_hours}h before event",
        ),
        _task(
            "signup_update",
            "Signup Update",
            enabled=event.discord_announcement and has_channel,
            log_source=None,
            check_interval="On signup change",
            description="Edits announcement embed with updated signup counts",
        ),
        _task(
            "open_signups",
            "Auto-Open Signups",
            enabled=bool(getattr(event, "signups_open_at", None)),
            fires_at=(
                event.signups_open_at
                if hasattr(event, "signups_open_at") and event.signups_open_at
                else None
            ),
            check_interval="Every 60s",
            description="Transitions event from upcoming to signups_open",
        ),
        _task(
            "draft_dm",
            "Team Draft DM",
            enabled=event.discord_send_draft_link and event.tournament_id is not None,
            log_source="draft_link",
            check_interval="On draft start",
            description="DMs participants the team draft link",
        ),
        _task(
            "herodraft_dm",
            "Hero Draft DM",
            enabled=event.discord_send_herodraft_link
            and event.tournament_id is not None,
            check_interval="On hero draft start",
            description="DMs participants the hero draft link",
        ),
    ]

    return Response(tasks)


FIREABLE_TASKS = {
    "announcement": "events.tasks.send_event_announcement",
    "signup_post": "events.tasks.send_event_announcement",
    "scheduled_event": "events.tasks.create_discord_scheduled_event",
    "signup_reminder": "events.tasks.send_subscriber_notifications",
    "confirm_attendance": "events.tasks.fire_event_reminder",
    "profile_reminder": "events.tasks.fire_event_reminder",
    "signup_update": "events.tasks.send_signup_update",
    "open_signups": "events.tasks.open_scheduled_signups",
    "draft_dm": "events.tournament_tasks.send_tournament_draft_links",
    "herodraft_dm": "events.tournament_tasks.send_tournament_herodraft_links",
}

# Map fire task names to their message log source for idempotency
TASK_LOG_SOURCES = {
    "announcement": "event_announcement",
    "confirm_attendance": "attendance_reminder",
    "profile_reminder": "profile_reminder",
}


@api_view(["POST"])
@permission_classes([permissions.IsAuthenticated])
def fire_event_task(request, event_id, task_name):
    """Manually fire a scheduled task for an event. Requires org staff access."""
    try:
        event = Event.objects.select_related("organization").get(pk=event_id)
    except Event.DoesNotExist:
        return Response({"error": "Event not found"}, status=status.HTTP_404_NOT_FOUND)

    if not has_org_staff_access(request.user, event.organization):
        return Response(
            {"error": "Staff access required"}, status=status.HTTP_403_FORBIDDEN
        )

    if task_name not in FIREABLE_TASKS:
        return Response(
            {"error": f"Unknown task: {task_name}"}, status=status.HTTP_400_BAD_REQUEST
        )

    if task_name == "scheduled_event" and not starts_in_future(event.scheduled_at):
        return Response(
            {"error": "Event start time has passed"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    # Idempotency: prevent double-fire for one-shot tasks (DMs). Repostable
    # tasks (signup_post, announcement) intentionally allow re-fire — the admin
    # is asking to push a fresh post — and we clear dedup state below before
    # invoking celery so the task recreates instead of no-opping.
    REPOSTABLE = {"signup_post", "announcement"}
    if task_name == "signup_reminder":
        from discordbot.models import DiscordEventDM, DMType

        if DiscordEventDM.objects.filter(
            discord_event__event_id=event_id,
            dm_type=DMType.SIGNUP_REMINDER,
        ).exists():
            return Response(
                {"error": "Signup reminder DMs have already been sent for this event"},
                status=status.HTTP_409_CONFLICT,
            )
    elif task_name not in REPOSTABLE:
        log_source = TASK_LOG_SOURCES.get(task_name)
        if log_source:
            from discordbot.models import DiscordMessageLog

            if DiscordMessageLog.objects.filter(
                source=log_source, source_id=event_id, success=True
            ).exists():
                return Response(
                    {"error": f"{task_name} has already been fired for this event"},
                    status=status.HTTP_409_CONFLICT,
                )

    # Repost path: clear DiscordEventMsgSignup.has_posted and DiscordMessageLog
    # success=True for source=event_announcement so send_event_announcement
    # actually recreates the post instead of being blocked by sync dedup
    # (sync_discord_events would otherwise skip; the manual-fire path bypasses
    # that, but we still clear so the next auto-sync agrees with the new state).
    if task_name in REPOSTABLE:
        from events.services import clear_signup_dedup_state

        clear_signup_dedup_state(event_id)

    from celery import current_app

    celery_task = FIREABLE_TASKS[task_name]

    # Signup reminder → send_subscriber_notifications (DMs, takes event_id only)
    if task_name == "signup_reminder":
        current_app.send_task(celery_task, args=[event_id])
    # Channel-post reminders: fire per-event with reminder_type and fired_by
    elif task_name in ("confirm_attendance", "profile_reminder"):
        current_app.send_task(
            celery_task,
            args=[event_id, task_name],
            kwargs={"fired_by_user_id": request.user.pk},
        )
    elif task_name == "draft_dm":
        if not event.tournament_id:
            return Response(
                {"error": "No tournament linked"}, status=status.HTTP_400_BAD_REQUEST
            )
        from app.models import Draft

        draft = Draft.objects.filter(tournament=event.tournament).first()
        if not draft:
            return Response(
                {"error": "No draft found for this tournament"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        current_app.send_task(celery_task, args=[event.tournament_id, draft.pk])
    elif task_name == "herodraft_dm":
        if not event.tournament_id:
            return Response(
                {"error": "No tournament linked"}, status=status.HTTP_400_BAD_REQUEST
            )
        from app.models import Game, HeroDraft

        game = Game.objects.filter(tournament=event.tournament).order_by("-pk").first()
        if not game:
            return Response(
                {"error": "No games found"}, status=status.HTTP_400_BAD_REQUEST
            )
        herodraft = HeroDraft.objects.filter(game=game).first()
        if not herodraft:
            return Response(
                {"error": "No hero draft found"}, status=status.HTTP_400_BAD_REQUEST
            )
        current_app.send_task(
            celery_task,
            args=[
                event.tournament_id,
                herodraft.pk,
                game.radiant_team.name if game.radiant_team else "Radiant",
                game.dire_team.name if game.dire_team else "Dire",
            ],
        )
    elif task_name in (
        "announcement",
        "signup_post",
        "scheduled_event",
        "signup_update",
    ):
        current_app.send_task(celery_task, args=[event_id])
    else:
        current_app.send_task(celery_task)

    logger.info(
        "task_manually_fired",
        system="events",
        subsystem="views",
        task_name=task_name,
        event_id=event_id,
        user_id=request.user.pk,
    )
    return Response({"fired": task_name, "event_id": event_id})
