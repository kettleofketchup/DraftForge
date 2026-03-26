import logging

from cacheops import invalidate_obj
from django.db import transaction
from django.db.models import BooleanField, Count, Exists, OuterRef, Q, Value
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied
from rest_framework.response import Response

logger = logging.getLogger(__name__)

from app.models import Organization
from app.permissions_org import has_org_staff_access
from events.models import (
    Event,
    EventRepeater,
    EventSignup,
    EventState,
    EventTeam,
    OrgEventDefaults,
    RepeaterSubscription,
    SignupStatus,
)
from events.serializers import (
    EventRepeaterSerializer,
    EventSerializer,
    EventSignupSerializer,
    EventTeamSerializer,
    OrgEventDefaultsSerializer,
)
from events.services import (
    approve_signup,
    cancel_signup,
    confirm_signup,
    create_tournament_for_event,
    demote_to_waitlist,
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

    def check_object_permissions(self, request, obj):
        super().check_object_permissions(request, obj)
        if self.action in ("update", "partial_update", "destroy"):
            if not has_org_staff_access(request.user, obj.organization):
                self.permission_denied(request)

    def get_queryset(self):
        qs = EventRepeater.objects.select_related(
            "organization", "tournament_league", "created_by"
        ).annotate(
            subscriber_count=Count("subscriptions"),
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
        return qs

    def perform_create(self, serializer):
        org = serializer.validated_data.get("organization")
        if not has_org_staff_access(self.request.user, org):
            raise PermissionDenied("You do not have staff access to this organization.")
        serializer.save(created_by=self.request.user)

    def perform_update(self, serializer):
        repeater = serializer.save()
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

    def get_queryset(self):
        qs = _annotate_event_qs(
            Event.objects.select_related(
                "organization", "tournament_league", "created_by", "tournament"
            )
        )
        org_id = self.request.query_params.get("organization")
        if org_id:
            qs = qs.filter(organization_id=org_id)
        state = self.request.query_params.get("state")
        if state:
            qs = qs.filter(state=state)
        return qs

    def perform_create(self, serializer):
        org = serializer.validated_data.get("organization")
        if not has_org_staff_access(self.request.user, org):
            raise PermissionDenied(
                "You do not have permission to create events for this organization."
            )
        event = serializer.save(created_by=self.request.user)
        create_tournament_for_event(event)
        # Auto-open signups if requested via query param
        if self.request.query_params.get("open_signups") == "true":
            try:
                event.transition_state(EventState.SIGNUPS_OPEN)
            except ValueError:
                pass  # Event already in a non-upcoming state
        from events.discord import notify_create_discord_event, notify_event_announced

        notify_event_announced(event)
        notify_create_discord_event(event)

    def perform_update(self, serializer):
        event = serializer.save()
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
    def open_signups(self, request, pk=None):
        event = self.get_object()
        if not has_org_staff_access(request.user, event.organization):
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
        if not has_org_staff_access(request.user, event.organization):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            event.transition_state(EventState.ROLL_CALL)
            qs = _annotate_event_qs(Event.objects.filter(pk=event.pk))
            return Response(EventSerializer(qs.first()).data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def start_tournament(self, request, pk=None):
        """Start the tournament (after roll call or directly)."""
        event = self.get_object()
        if not has_org_staff_access(request.user, event.organization):
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
            qs = _annotate_event_qs(Event.objects.filter(pk=event.pk))
            return Response(EventSerializer(qs.first()).data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def perform_destroy(self, instance):
        """Clean up tournament and Discord messages before deleting event."""
        with transaction.atomic():
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
        if not has_org_staff_access(request.user, event.organization):
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

        from discordbot.serializers_discord_event import DiscordEventDetailSerializer

        @cached_as(
            DiscordEvent,
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
        if not has_org_staff_access(request.user, event.organization):
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
        if not has_org_staff_access(request.user, signup.event.organization):
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
        if not has_org_staff_access(request.user, signup.event.organization):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            return Response(EventSignupSerializer(reject_signup(signup)).data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def confirm(self, request, pk=None):
        signup = self.get_object()
        if not has_org_staff_access(request.user, signup.event.organization):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            return Response(EventSignupSerializer(confirm_signup(signup)).data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def cancel_signup(self, request, pk=None):
        signup = self.get_object()
        if signup.user != request.user and not has_org_staff_access(
            request.user, signup.event.organization
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
        if not has_org_staff_access(request.user, signup.event.organization):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            return Response(EventSignupSerializer(unconfirm_signup(signup)).data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def demote(self, request, pk=None):
        """Move an active signup to the end of the waitlist."""
        signup = self.get_object()
        if not has_org_staff_access(request.user, signup.event.organization):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            return Response(EventSignupSerializer(demote_to_waitlist(signup)).data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def reinstate(self, request, pk=None):
        """Reinstate a cancelled signup (user can reinstate their own)."""
        signup = self.get_object()
        if signup.user != request.user and not has_org_staff_access(
            request.user, signup.event.organization
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
        event = Event.objects.select_related("organization", "event_repeater").get(
            pk=event_id
        )
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

    def _task(
        task, label, enabled, fires_at=None, log_source=None, misconfigured=False
    ):
        """Build a task entry with status."""
        if misconfigured:
            return {
                "task": task,
                "label": label,
                "fires_at": None,
                "status": "misconfigured",
            }
        if not enabled:
            return {
                "task": task,
                "label": label,
                "fires_at": None,
                "status": "disabled",
            }

        # Determine status
        if task == "subscriber_dm":
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

        return {
            "task": task,
            "label": label,
            "fires_at": fires_at.isoformat() if fires_at else None,
            "status": s,
        }

    has_channel = bool(event.discord_announcement_channel_id)

    tasks = [
        _task(
            "announcement",
            "Discord Announcement",
            enabled=event.discord_announcement and has_channel,
            log_source="event_announcement",
            misconfigured=event.discord_announcement and not has_channel,
        ),
        _task(
            "signup_post",
            "Signup Post",
            enabled=event.discord_post_signups
            and bool(event.discord_post_signups_channel_id),
            misconfigured=event.discord_post_signups
            and not event.discord_post_signups_channel_id,
        ),
        _task(
            "scheduled_event",
            "Discord Scheduled Event",
            enabled=event.discord_create_event
            and bool(event.organization.discord_server_id),
            misconfigured=event.discord_create_event
            and not event.organization.discord_server_id,
        ),
        _task(
            "signup_reminder",
            "Signup Reminder",
            enabled=event.discord_signup_reminder and has_channel,
            fires_at=(
                event.scheduled_at
                - timedelta(hours=event.discord_signup_reminder_hours)
                if event.discord_signup_reminder
                else None
            ),
            log_source="signup_reminder",
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
        ),
        _task(
            "subscriber_dm",
            "Subscriber DM",
            enabled=event.discord_subscriber_dm and event.event_repeater_id is not None,
            fires_at=(
                event.scheduled_at - timedelta(hours=event.discord_subscriber_dm_hours)
                if event.discord_subscriber_dm
                else None
            ),
        ),
        _task(
            "signup_update",
            "Signup Update",
            enabled=event.discord_announcement and has_channel,
            log_source=None,  # event-triggered, not time-based
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
        ),
    ]

    return Response(tasks)
