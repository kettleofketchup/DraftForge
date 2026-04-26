import logging

from cacheops import cached_as, invalidate_obj
from django.db import transaction
from django.db.models import BooleanField, Count, Exists, F, OuterRef, Q, Value
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

logger = logging.getLogger(__name__)

from app.models import Organization
from app.permissions_org import has_event_staff_access, has_org_staff_access
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
)
from events.services import (
    approve_signup,
    cancel_signup,
    confirm_signup,
    create_tournament_for_event,
    demote_to_waitlist,
    ensure_discord_event,
    finalize_event_tournament,
    process_rsvp,
    reinstate_signup,
    reject_signup,
    restart_event_tournament,
    sync_future_events,
    sync_tournament_from_event,
    unconfirm_signup,
)


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

        repeater = serializer.save()
        invalidate_after_commit(repeater)
        sync_future_events(repeater)

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
        subs = RepeaterSubscription.objects.filter(
            event_repeater=repeater
        ).select_related("user")
        from events.serializers import RepeaterSubscriptionSerializer

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

        return Response(get_data())

    def retrieve(self, request, *args, **kwargs):
        pk = kwargs.get("pk")
        cache_key = f"event_detail:{pk}"

        @cached_as(
            Event.objects.filter(pk=pk),
            EventSignup,
            keep_fresh=True,
            extra=cache_key,
            timeout=60 * 60,
        )
        def get_data():
            instance = self.get_object()
            return self.get_serializer(instance).data

        return Response(get_data())

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
        from events.discord import notify_create_discord_event, notify_event_announced

        notify_event_announced(event)
        notify_create_discord_event(event)

    def perform_update(self, serializer):
        from app.cache_utils import invalidate_after_commit

        event = serializer.save()
        invalidate_after_commit(event)
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
                from events.discord import (
                    notify_create_discord_event,
                    notify_event_announced,
                )

                notify_event_announced(event)
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
        detail=True, methods=["post"], permission_classes=[permissions.IsAuthenticated]
    )
    def rsvp(self, request, pk=None):
        event = self.get_object()
        logger.info(
            "RSVP request: user=%s (pk=%s), event=%s (pk=%s, state=%s)",
            request.user.username,
            request.user.pk,
            event.name,
            event.pk,
            event.state,
        )
        try:
            signup = process_rsvp(event, request.user)
            logger.info(
                "RSVP success: user=%s, event=%s, status=%s",
                request.user.pk,
                event.pk,
                signup.status,
            )
            return Response(
                EventSignupSerializer(signup).data, status=status.HTTP_201_CREATED
            )
        except ValueError as e:
            logger.warning(
                "RSVP rejected: user=%s, event=%s, reason=%s",
                request.user.pk,
                event.pk,
                str(e),
            )
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def tentative(self, request, pk=None):
        """Mark yourself as tentative for an event (interested but not committed).
        POST /api/events/<pk>/tentative/
        """
        event = self.get_object()
        if event.state != EventState.SIGNUPS_OPEN:
            return Response(
                {"error": "Event is not accepting signups"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Check for existing active signup
        existing = (
            EventSignup.objects.filter(event=event, user=request.user)
            .exclude(status__in=[SignupStatus.CANCELLED, SignupStatus.REJECTED])
            .first()
        )
        if existing:
            if existing.status == SignupStatus.TENTATIVE:
                return Response(
                    {"error": "Already marked as tentative"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            return Response(
                {"error": f"Already signed up (status: {existing.status})"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Delete cancelled/rejected signup to allow fresh tentative
        EventSignup.objects.filter(
            event=event,
            user=request.user,
            status__in=[SignupStatus.CANCELLED, SignupStatus.REJECTED],
        ).delete()
        signup = EventSignup.objects.create(
            event=event, user=request.user, status=SignupStatus.TENTATIVE
        )
        from app.cache_utils import invalidate_after_commit

        invalidate_after_commit(signup, event)
        return Response(
            EventSignupSerializer(signup).data, status=status.HTTP_201_CREATED
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
            signup = process_rsvp(event, user)
            return Response(
                EventSignupSerializer(signup).data, status=status.HTTP_201_CREATED
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
            from events.discord import notify_event_announced

            notify_event_announced(event)
            qs = _annotate_event_qs(Event.objects.filter(pk=event.pk))
            return Response(EventSerializer(qs.first()).data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def start_roll_call(self, request, pk=None):
        event = self.get_object()
        if not has_event_staff_access(request.user, event):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            event.transition_state(EventState.ROLL_CALL)
            qs = _annotate_event_qs(Event.objects.filter(pk=event.pk))
            return Response(EventSerializer(qs.first()).data)
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
            qs = _annotate_event_qs(Event.objects.filter(pk=event.pk))
            return Response(EventSerializer(qs.first()).data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def start_tournament(self, request, pk=None):
        """Start the tournament (after roll call or directly)."""
        event = self.get_object()
        if not has_event_staff_access(request.user, event):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            if event.state == EventState.ROLL_CALL:
                event.transition_state(EventState.IN_PROGRESS)
            elif event.state == EventState.SIGNUPS_OPEN:
                event.transition_state(EventState.IN_PROGRESS)
            else:
                return Response(
                    {"error": f"Cannot start tournament from '{event.state}' state."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            finalize_event_tournament(event)
            # Start auto-create herodrafts polling if enabled
            if event.tournament and event.tournament.auto_create_hero_drafts:
                from events.discord.tournament_dispatch import (
                    start_auto_create_herodrafts,
                )

                start_auto_create_herodrafts(event.tournament)
            qs = _annotate_event_qs(Event.objects.filter(pk=event.pk))
            return Response(EventSerializer(qs.first()).data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def perform_destroy(self, instance):
        """Clean up tournament and Discord messages before deleting event."""
        from app.cache_utils import invalidate_after_commit

        with transaction.atomic():
            invalidate_after_commit(instance)
            # Delete linked tournament
            if instance.tournament:
                tournament = instance.tournament
                instance.tournament = None
                instance.save(update_fields=["tournament", "updated_at"])
                tournament.delete()

            # Delete DiscordEvent (cascades to messages, logs, DMs)
            from discordbot.models import DiscordEvent

            try:
                discord_event = instance.discord_event
                discord_event.delete()
            except DiscordEvent.DoesNotExist:
                pass

            # Clean up legacy DiscordMessageLog entries for pre-migration data
            from discordbot.models import DiscordMessageLog

            DiscordMessageLog.objects.filter(
                source__in=["event_announcement", "event_notice"],
                source_id=instance.pk,
            ).delete()

            instance.delete()

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        event = self.get_object()
        if not has_event_staff_access(request.user, event):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            with transaction.atomic():
                # Delete linked tournament before cancelling
                if event.tournament:
                    tournament = event.tournament
                    event.tournament = None
                    event.save(update_fields=["tournament", "updated_at"])
                    tournament.delete()
                event.transition_state(EventState.CANCELLED)
            qs = _annotate_event_qs(Event.objects.filter(pk=event.pk))
            return Response(EventSerializer(qs.first()).data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

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
            qs = _annotate_event_qs(Event.objects.filter(pk=event.pk))
            return Response(EventSerializer(qs.first()).data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class EventSignupViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EventSignupSerializer
    permission_classes = [permissions.AllowAny]

    def get_queryset(self):
        qs = EventSignup.objects.select_related("user", "event", "event_team")
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

        return Response(EventSignupSerializer(result).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        signup = self.get_object()
        if not has_event_staff_access(request.user, signup.event):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            return Response(EventSignupSerializer(reject_signup(signup)).data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        signup = self.get_object()
        if not has_event_staff_access(request.user, signup.event):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            return Response(EventSignupSerializer(confirm_signup(signup)).data)
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
            return Response(EventSignupSerializer(cancel_signup(signup)).data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def unconfirm(self, request, pk=None):
        """Revert a confirmed signup back to approved."""
        signup = self.get_object()
        if not has_event_staff_access(request.user, signup.event):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            return Response(EventSignupSerializer(unconfirm_signup(signup)).data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def demote(self, request, pk=None):
        """Move an active signup to the end of the waitlist."""
        signup = self.get_object()
        if not has_event_staff_access(request.user, signup.event):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            return Response(EventSignupSerializer(demote_to_waitlist(signup)).data)
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
            return Response(EventSignupSerializer(reinstate_signup(signup)).data)
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

        entry["status"] = s
        entry["can_fire"] = s in ("ready", "pending")
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

    # Idempotency: prevent double-fire
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
    else:
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
        "Manual fire: task=%s event=%s by user=%s",
        task_name,
        event_id,
        request.user.pk,
    )
    return Response({"fired": task_name, "event_id": event_id})
