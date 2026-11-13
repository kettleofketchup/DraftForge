from typing import Any

from django.contrib.auth.models import AnonymousUser
from django.db.models import Count, Sum
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.exceptions import NotAuthenticated, ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from app.models import CustomUser, Organization
from app.permissions_org import can_view_org_members, has_org_staff_access
from events.models import Event
from org.contributions.kinds import DEFAULT_POINTS, RATED_KINDS, ContributionKind
from org.contributions.periods import Period, parse_period
from org.contributions.queries import (
    LeaderboardRow,
    leaderboard,
    member_entries,
    member_monthly,
    member_totals,
    org_total,
)
from org.contributions.serializers import (
    EntriesQuerySerializer,
    ManualAwardCreateSerializer,
    ManualAwardUpdateSerializer,
    PeriodQuerySerializer,
    PointValueUpdateSerializer,
    admin_entry_data,
    entry_data,
    member_summary,
)
from org.contributions.services import (
    create_manual_award,
    delete_manual_award,
    set_point_value,
    update_manual_award,
)
from org.feature_errors import not_permitted, require_feature, require_org_admin
from org.features import FeatureKey
from org.models import ContributionEntry, ContributionPointValue, OrgUser
from user.querysets import with_user_profiles


def _org(org_id: int) -> Organization:
    org = get_object_or_404(Organization, pk=org_id)
    require_feature(org, FeatureKey.CONTRIBUTIONS)
    return org


def _admin_org(request: Request, org_id: int) -> Organization:
    org = get_object_or_404(Organization, pk=org_id)
    require_org_admin(request.user, org, FeatureKey.CONTRIBUTIONS)
    return org


def _period(request: Request, org: Organization) -> Period:
    query = PeriodQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    return _parse_period(org, query.validated_data.get("period"))


def _parse_period(org: Organization, value: str | None) -> Period:
    try:
        return parse_period(org, value)
    except ValueError as exc:
        raise ValidationError({"period": str(exc)}) from exc


def _own_org_user(
    user: CustomUser | AnonymousUser, org: Organization
) -> OrgUser | None:
    if not user.is_authenticated:
        return None
    return with_user_profiles(
        OrgUser.objects.filter(organization=org, user_id=user.pk), "user"
    ).first()


def _own_row(org_user: OrgUser, period: Period) -> LeaderboardRow | None:
    sums = member_entries(org_user, period).aggregate(
        total=Sum("points"), entries=Count("pk")
    )
    if not sums["entries"]:
        return None
    return LeaderboardRow(
        **member_summary(org_user),
        points=sums["total"] or 0,
        entries=sums["entries"],
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def contributions_leaderboard(request: Request, org_id: int) -> Response:
    org = _org(org_id)
    period = _period(request, org)
    rows_visible = can_view_org_members(request.user, org)
    own = _own_org_user(request.user, org)
    return Response(
        {
            "period": period.label,
            "total": org_total(org, period),
            "rows_visible": rows_visible,
            "rows": leaderboard(org, period) if rows_visible else [],
            "own_row": _own_row(own, period) if own is not None else None,
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def contributions_member(request: Request, org_id: int, org_user_pk: int) -> Response:
    org = _org(org_id)
    org_user = get_object_or_404(
        with_user_profiles(OrgUser.objects.filter(organization=org), "user"),
        pk=org_user_pk,
    )
    org_user.organization = org
    user = request.user
    is_own = user.is_authenticated and org_user.user_id == user.pk
    if not is_own and not can_view_org_members(user, org):
        if not user.is_authenticated:
            raise NotAuthenticated()
        raise not_permitted()
    period = _period(request, org)
    with_reason = has_org_staff_access(user, org)
    return Response(
        {
            "member": member_summary(org_user),
            "totals": member_totals(org_user),
            "monthly": member_monthly(org_user),
            "entries": [
                entry_data(entry, with_reason=with_reason)
                for entry in member_entries(org_user, period)
            ],
        }
    )


def _point_values(org: Organization) -> list[dict[str, Any]]:
    overrides = dict(
        ContributionPointValue.objects.nocache()
        .filter(organization=org)
        .values_list("kind", "points")
    )
    result: list[dict[str, Any]] = []
    for kind in RATED_KINDS:
        default = DEFAULT_POINTS[kind.value]
        override = overrides.get(kind.value)
        result.append(
            {
                "kind": kind.value,
                "points": default if override is None else override,
                "default": default,
                "is_default": override is None,
            }
        )
    return result


@api_view(["GET"])
@permission_classes([AllowAny])
def contributions_point_values(request: Request, org_id: int) -> Response:
    org = _admin_org(request, org_id)
    return Response(_point_values(org))


@api_view(["PUT"])
@parser_classes([JSONParser])
@permission_classes([AllowAny])
def contributions_point_value(request: Request, org_id: int, kind: str) -> Response:
    org = _admin_org(request, org_id)
    if kind not in {k.value for k in RATED_KINDS}:
        raise ValidationError({"kind": f"{kind!r} has no point value"})
    body = PointValueUpdateSerializer(data=request.data)
    body.is_valid(raise_exception=True)
    data = body.validated_data
    try:
        result = set_point_value(
            org,
            kind,
            data["points"],
            actor=request.user,
            apply_to_past=data["apply_to_past"],
            since=data["since"],
        )
    except ValueError as exc:
        raise ValidationError({"detail": str(exc)}) from exc
    return Response(
        {"kind": kind, "old": result.old, "new": result.new, "changed": result.changed}
    )


def _org_event(org: Organization, event_id: int | None) -> Event | None:
    if event_id is None:
        return None
    event = Event.objects.filter(pk=event_id, organization=org).first()
    if event is None:
        raise ValidationError({"event_id": "event not found in this organization"})
    return event


def _admin_entry(entry_pk: int) -> ContributionEntry:
    return with_user_profiles(
        ContributionEntry.objects.select_related("event", "awarded_by"),
        "org_user__user",
    ).get(pk=entry_pk)


def _list_entries(request: Request, org: Organization) -> Response:
    query = EntriesQuerySerializer(data=request.query_params)
    query.is_valid(raise_exception=True)
    params = query.validated_data
    period = _parse_period(org, params.get("period"))
    qs = ContributionEntry.objects.nocache().filter(organization=org)
    if period.start is not None:
        qs = qs.filter(occurred_at__gte=period.start)
    if period.end is not None:
        qs = qs.filter(occurred_at__lt=period.end)
    if "kind" in params:
        qs = qs.filter(kind=params["kind"])
    if "member" in params:
        qs = qs.filter(org_user_id=params["member"])
    qs = with_user_profiles(
        qs.select_related("event", "awarded_by"), "org_user__user"
    ).order_by("-occurred_at", "-pk")
    offset, limit = params["offset"], params["limit"]
    return Response(
        {
            "count": qs.count(),
            "limit": limit,
            "offset": offset,
            "results": [admin_entry_data(e) for e in qs[offset : offset + limit]],
        }
    )


def _create_entry(request: Request, org: Organization) -> Response:
    body = ManualAwardCreateSerializer(data=request.data)
    body.is_valid(raise_exception=True)
    data = body.validated_data
    user = CustomUser.objects.filter(pk=data["user_id"]).first()
    if user is None:
        raise ValidationError({"user_id": "user not found"})
    event = _org_event(org, data.get("event_id"))
    try:
        entry = create_manual_award(
            org=org,
            user=user,
            points=data["points"],
            reason=data["reason"],
            on_date=data["date"],
            actor=request.user,
            event=event,
        )
    except ValueError as exc:
        raise ValidationError({"detail": str(exc)}) from exc
    return Response(
        admin_entry_data(_admin_entry(entry.pk)), status=status.HTTP_201_CREATED
    )


@api_view(["GET", "POST"])
@parser_classes([JSONParser])
@permission_classes([AllowAny])
def contributions_entries(request: Request, org_id: int) -> Response:
    org = _admin_org(request, org_id)
    if request.method == "POST":
        return _create_entry(request, org)
    return _list_entries(request, org)


@api_view(["PATCH", "DELETE"])
@parser_classes([JSONParser])
@permission_classes([AllowAny])
def contributions_entry(request: Request, org_id: int, entry_pk: int) -> Response:
    org = _admin_org(request, org_id)
    entry = get_object_or_404(
        ContributionEntry.objects.nocache().select_related(
            "organization", "org_user__user"
        ),
        pk=entry_pk,
        organization=org,
    )
    if entry.kind != ContributionKind.MANUAL:
        raise ValidationError({"detail": "only manual awards can be edited or deleted"})

    if request.method == "DELETE":
        delete_manual_award(entry, actor=request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)

    body = ManualAwardUpdateSerializer(data=request.data)
    body.is_valid(raise_exception=True)
    data = body.validated_data
    changes: dict[str, Any] = {}
    if "event_id" in data:
        changes["event"] = _org_event(org, data["event_id"])
    try:
        entry = update_manual_award(
            entry,
            actor=request.user,
            points=data.get("points"),
            reason=data.get("reason"),
            on_date=data.get("date"),
            **changes,
        )
    except ValueError as exc:
        raise ValidationError({"detail": str(exc)}) from exc
    return Response(admin_entry_data(_admin_entry(entry.pk)))
