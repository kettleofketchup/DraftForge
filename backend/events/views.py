from django.db.models import Count, Q
from rest_framework import permissions, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from app.permissions_org import has_org_staff_access
from events.models import (
    Event,
    EventRepeater,
    EventSignup,
    EventState,
    EventTeam,
    SignupStatus,
)
from events.serializers import (
    EventRepeaterSerializer,
    EventSerializer,
    EventSignupSerializer,
    EventTeamSerializer,
)
from events.services import (
    approve_signup,
    auto_start_event,
    cancel_signup,
    confirm_signup,
    process_rsvp,
    reject_signup,
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
    permission_classes = [permissions.IsAuthenticated, IsOrgStaff]

    def get_queryset(self):
        qs = EventRepeater.objects.select_related(
            "organization", "tournament_league", "created_by"
        )
        org_id = self.request.query_params.get("organization")
        if org_id:
            qs = qs.filter(organization_id=org_id)
        return qs

    def perform_create(self, serializer):
        serializer.save(created_by=self.request.user)


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
        serializer.save(created_by=self.request.user)

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
        try:
            signup = process_rsvp(event, request.user)
            return Response(
                EventSignupSerializer(signup).data, status=status.HTTP_201_CREATED
            )
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def open_signups(self, request, pk=None):
        event = self.get_object()
        if not has_org_staff_access(request.user, event.organization):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            event.transition_state(EventState.SIGNUPS_OPEN)
            return Response(EventSerializer(event).data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def start_roll_call(self, request, pk=None):
        event = self.get_object()
        if not has_org_staff_access(request.user, event.organization):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            event.transition_state(EventState.ROLL_CALL)
            return Response(EventSerializer(event).data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=["post"])
    def start_tournament(self, request, pk=None):
        """Manual tournament start (after roll call). Creates tournament from event config."""
        event = self.get_object()
        if not has_org_staff_access(request.user, event.organization):
            return Response(status=status.HTTP_403_FORBIDDEN)
        original_auto_start = event.auto_start
        try:
            event.auto_start = True
            if event.state == EventState.ROLL_CALL:
                event.state = EventState.SIGNUPS_OPEN
            tournament = auto_start_event(event)
            if tournament:
                event.refresh_from_db()
                return Response(EventSerializer(event).data)
            return Response(
                {"error": "Could not start tournament."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            event.auto_start = original_auto_start
            raise

    @action(detail=True, methods=["post"])
    def cancel(self, request, pk=None):
        event = self.get_object()
        if not has_org_staff_access(request.user, event.organization):
            return Response(status=status.HTTP_403_FORBIDDEN)
        try:
            event.transition_state(EventState.CANCELLED)
            return Response(EventSerializer(event).data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class EventSignupViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = EventSignupSerializer
    permission_classes = [permissions.IsAuthenticated]

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
        try:
            return Response(EventSignupSerializer(approve_signup(signup)).data)
        except ValueError as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

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


class EventTeamViewSet(viewsets.ModelViewSet):
    serializer_class = EventTeamSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = EventTeam.objects.select_related("event", "captain").annotate(
            member_count=Count("members"),
        )
        event_id = self.request.query_params.get("event")
        if event_id:
            qs = qs.filter(event_id=event_id)
        return qs
