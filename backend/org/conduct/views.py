from datetime import timedelta
from typing import Any

from django.contrib.auth.models import AnonymousUser
from django.db import transaction
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.exceptions import NotAuthenticated, ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from app.models import CustomUser
from app.permissions_tournament import has_event_staff_access
from events.constants import SignupStatus
from events.models import Event, EventSignup
from org.conduct.attendance import event_attendance, event_forecast
from org.conduct.constants import Outcome, expected_statuses
from org.conduct.gate import get_conduct_settings
from org.conduct.leaderboard import conduct_board
from org.conduct.params import rate_params
from org.conduct.queries import member_scores
from org.conduct.serializers import (
    AttendancePutSerializer,
    ConductSettingsUpdateSerializer,
    HistoryQuerySerializer,
    history_item,
    leaderboard_row,
    new_member_row,
    own_row,
    rate,
    settings_data,
)
from org.conduct.services import set_outcomes, update_conduct_settings
from org.contributions.serializers import member_summary
from org.feature_errors import not_permitted, require_feature, require_org_admin
from org.features import FeatureKey
from org.membership import resolve_or_create_org_user
from org.models import Organization, OrgUser
from org.models_conduct import AttendanceOutcome
from org.permissions import can_view_org_members, has_org_staff_access
from user.querysets import with_user_profiles

TOTAL_OUTCOMES: tuple[Outcome, ...] = (
    Outcome.ATTENDED,
    Outcome.NO_SHOW,
    Outcome.LATE_CANCEL,
    Outcome.EXCUSED,
)


def _org(org_id: int) -> Organization:
    org = get_object_or_404(Organization, pk=org_id)
    require_feature(org, FeatureKey.CONDUCT)
    return org


def _admin_org(request: Request, org_id: int) -> Organization:
    org = get_object_or_404(Organization, pk=org_id)
    require_org_admin(request.user, org, FeatureKey.CONDUCT)
    return org


@api_view(["GET", "PATCH"])
@parser_classes([JSONParser])
@permission_classes([AllowAny])
def conduct_settings(request: Request, org_id: int) -> Response:
    org = _admin_org(request, org_id)
    row = get_conduct_settings(org)
    if request.method == "PATCH":
        body = ConductSettingsUpdateSerializer(
            data=request.data, context={"current": row}
        )
        body.is_valid(raise_exception=True)
        try:
            row = update_conduct_settings(
                org, actor=request.user, changes=body.validated_data
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
    return Response(settings_data(row))


def _own_org_user(
    user: CustomUser | AnonymousUser, org: Organization
) -> OrgUser | None:
    if not user.is_authenticated:
        return None
    return with_user_profiles(
        OrgUser.objects.filter(organization=org, user_id=user.pk), "user"
    ).first()


@api_view(["GET"])
@permission_classes([AllowAny])
def conduct_leaderboard(request: Request, org_id: int) -> Response:
    org = _org(org_id)
    user = request.user
    settings = get_conduct_settings(org)
    own = _own_org_user(user, org)
    rows_visible = can_view_org_members(user, org)
    if not settings.leaderboard_public and not has_org_staff_access(user, org):
        if not user.is_authenticated:
            raise NotAuthenticated()
        if own is None:
            raise not_permitted()
        rows_visible = False

    board = conduct_board(org, own=own, now=timezone.now(), settings=settings)
    ranked = board.ranked
    new = board.new
    own_data = own_row(*board.own) if board.own is not None else None
    return Response(
        {
            "rows_visible": rows_visible,
            "rows": (
                [leaderboard_row(m, s, r) for m, s, r in ranked] if rows_visible else []
            ),
            "new_members": (
                [new_member_row(m, s) for m, s in new] if rows_visible else []
            ),
            "own_row": own_data,
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def conduct_member(request: Request, org_id: int, org_user_pk: int) -> Response:
    org = _org(org_id)
    org_user = get_object_or_404(
        with_user_profiles(OrgUser.objects.filter(organization=org), "user"),
        pk=org_user_pk,
    )
    user = request.user
    is_own = user.is_authenticated and org_user.user_id == user.pk
    is_staff = has_org_staff_access(user, org)
    if not is_own and not is_staff:
        if not user.is_authenticated:
            raise NotAuthenticated()
        raise not_permitted()
    query = HistoryQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    offset: int = query.validated_data["offset"]
    limit: int = query.validated_data["limit"]

    settings = get_conduct_settings(org)
    params = rate_params(settings)
    now = timezone.now()
    cutoff = now - timedelta(days=params.max_age_days)
    score = member_scores(org.pk, [org_user.pk], now=now, settings=settings)[
        org_user.pk
    ]
    rows = AttendanceOutcome.objects.nocache().filter(org_user=org_user)
    totals = rows.filter(
        finalized_at__isnull=False,
        voided_at__isnull=True,
        committed=True,
        event_starts_at__gte=cutoff,
    ).aggregate(
        **{
            outcome.value: Count("pk", filter=Q(outcome=outcome))
            for outcome in TOTAL_OUTCOMES
        }
    )
    history = rows.select_related("set_by").order_by("-event_starts_at", "-pk")[
        offset : offset + limit
    ]
    return Response(
        {
            "member": member_summary(org_user),
            "show_rate": rate(score.show_rate),
            "status": score.status,
            "counted_events": score.counted_events,
            "weighted_events": rate(score.weighted_events),
            "totals": totals,
            "history": [
                history_item(
                    row,
                    now=now,
                    cutoff=cutoff,
                    half_life_days=params.half_life_days,
                    with_reason=is_staff,
                )
                for row in history
            ],
        }
    )


def _staff_event(request: Request, org_id: int, event_id: int) -> Event:
    org = _org(org_id)
    event = get_object_or_404(
        Event.objects.nocache().select_related("organization", "tournament_league"),
        pk=event_id,
        organization=org,
    )
    user = request.user
    if not has_event_staff_access(user, event):
        if not user.is_authenticated:
            raise NotAuthenticated()
        raise not_permitted()
    return event


def _resolve_changes(
    event: Event, changes: list[dict[str, Any]]
) -> list[tuple[OrgUser, Outcome]]:
    members = OrgUser.objects.nocache().filter(organization_id=event.organization_id)
    org_user_pks = {c["org_user_pk"] for c in changes if "org_user_pk" in c}
    user_pks = {c["user_pk"] for c in changes if "user_pk" in c}
    by_pk = members.filter(pk__in=org_user_pks).in_bulk()
    by_user = {ou.user_id: ou for ou in members.filter(user_id__in=user_pks)}
    signed_up = {
        signup.user_id: signup.user
        for signup in EventSignup.objects.nocache()
        .filter(
            event_id=event.pk,
            user_id__in=user_pks,
            status__in=expected_statuses(event) | {SignupStatus.DROPPED},
        )
        .select_related("user")
    }
    resolved: list[tuple[OrgUser, Outcome]] = []
    for change in changes:
        outcome = Outcome(change["outcome"])
        if "org_user_pk" in change:
            org_user = by_pk.get(change["org_user_pk"])
        else:
            user_pk = change["user_pk"]
            signup_user = signed_up.get(user_pk)
            if signup_user is None and outcome != Outcome.ATTENDED:
                raise ValidationError(
                    {"outcome": "A walk-in can only be marked attended."}
                )
            org_user = by_user.get(user_pk)
            if org_user is None and signup_user is not None:
                org_user = resolve_or_create_org_user(signup_user, event.organization)
        if org_user is None:
            raise ValidationError({"changes": "member not found in this organization"})
        resolved.append((org_user, outcome))
    return resolved


@api_view(["GET", "PUT"])
@parser_classes([JSONParser])
@permission_classes([AllowAny])
def conduct_event_attendance(request: Request, org_id: int, event_id: int) -> Response:
    event = _staff_event(request, org_id, event_id)
    if request.method == "PUT":
        body = AttendancePutSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                set_outcomes(
                    event,
                    actor=request.user,
                    changes=_resolve_changes(event, body.validated_data["changes"]),
                    reason=body.validated_data["reason"],
                )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        event = Event.objects.nocache().get(pk=event.pk)
    return Response(event_attendance(event, now=timezone.now()))


@api_view(["GET"])
@permission_classes([AllowAny])
def conduct_event_forecast(request: Request, org_id: int, event_id: int) -> Response:
    event = _staff_event(request, org_id, event_id)
    return Response(event_forecast(event, now=timezone.now()))
