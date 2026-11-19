from datetime import timedelta

from django.contrib.auth.models import AnonymousUser
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.exceptions import NotAuthenticated, ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from app.models import CustomUser, Organization
from app.permissions_org import can_view_org_members, has_org_staff_access
from org.conduct.constants import Outcome
from org.conduct.gate import get_conduct_settings
from org.conduct.queries import member_scores
from org.conduct.scoring import MemberScore, ScoreParams, prior_score
from org.conduct.serializers import (
    ConductSettingsUpdateSerializer,
    HistoryQuerySerializer,
    history_item,
    leaderboard_row,
    new_member_row,
    own_row,
    rate,
    settings_data,
)
from org.conduct.services import update_conduct_settings
from org.contributions.serializers import member_summary
from org.feature_errors import not_permitted, require_feature, require_org_admin
from org.features import FeatureKey
from org.models import OrgUser
from org.models_conduct import AttendanceOutcome
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


def _sort_name(org_user: OrgUser) -> str:
    user = org_user.user
    return (user.nickname or user.username).casefold()


def _ranked(
    scored: list[tuple[OrgUser, MemberScore]],
) -> list[tuple[OrgUser, MemberScore, int]]:
    ordered = sorted(
        scored,
        key=lambda pair: (
            -rate(pair[1].show_rate),
            -pair[1].counted_events,
            _sort_name(pair[0]),
            pair[0].pk,
        ),
    )
    result: list[tuple[OrgUser, MemberScore, int]] = []
    rank = 0
    previous: tuple[float, int] | None = None
    for org_user, score in ordered:
        key = (rate(score.show_rate), score.counted_events)
        if key != previous:
            rank += 1
            previous = key
        result.append((org_user, score, rank))
    return result


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

    now = timezone.now()
    scores = member_scores(org.pk, None, now=now, settings=settings)
    members = with_user_profiles(
        OrgUser.objects.filter(pk__in=scores), "user"
    ).in_bulk()
    ranked = _ranked(
        [
            (members[pk], score)
            for pk, score in scores.items()
            if score.status == "scored" and pk in members
        ]
    )
    ranks = {org_user.pk: rank for org_user, _, rank in ranked}
    new = sorted(
        (
            (members[pk], score)
            for pk, score in scores.items()
            if score.status == "new" and pk in members
        ),
        key=lambda pair: (-pair[1].counted_events, _sort_name(pair[0]), pair[0].pk),
    )
    own_data = None
    if own is not None:
        own_score = scores.get(own.pk) or prior_score(
            ScoreParams.from_settings(settings)
        )
        own_data = own_row(own, own_score, ranks.get(own.pk))
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
    params = ScoreParams.from_settings(settings)
    now = timezone.now()
    cutoff = now - timedelta(days=params.max_age_days)
    score = member_scores(org.pk, [org_user.pk], now=now, settings=settings).get(
        org_user.pk
    ) or prior_score(params)
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
