from typing import Any

from django.contrib.auth.models import AnonymousUser
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import (
    api_view,
    parser_classes,
    permission_classes,
    throttle_classes,
)
from rest_framework.exceptions import (
    APIException,
    NotAuthenticated,
    NotFound,
    ValidationError,
)
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle

from app.models import CustomUser
from events.models import Event
from org.contributions.serializers import member_summary
from org.feature_errors import not_permitted, require_feature, require_org_admin
from org.features import FeatureKey
from org.leadership.reviews import (
    ReviewRefused,
    submit_review,
    unvoid_review,
    void_review,
    withdraw_review,
)
from org.leadership.serializers import (
    ReasonSerializer,
    ReviewPutSerializer,
    SettingsUpdateSerializer,
    TraitsPutSerializer,
    settings_data,
)
from org.leadership.settings import (
    get_leadership_settings,
    kind_points,
    update_leadership_settings,
)
from org.leadership.summary import member_payload, trait_data
from org.leadership.traits import (
    TraitInUse,
    delete_trait,
    effective_traits,
    upsert_traits,
)
from org.models import Organization, OrgUser
from org.models_leadership import CaptainReview, CaptainTrait, EventCaptain
from org.permissions import can_view_org_members, has_org_admin_access
from user.querysets import with_user_profiles


class CaptainReviewThrottle(UserRateThrottle):
    scope = "captain_review"
    rate = "30/min"


class Refused(APIException):
    def __init__(self, exc: ReviewRefused) -> None:
        super().__init__(detail={"code": exc.code, "detail": exc.detail})
        self.status_code = exc.status


def _org(org_id: int) -> Organization:
    org = get_object_or_404(Organization, pk=org_id)
    require_feature(org, FeatureKey.LEADERSHIP)
    return org


def _admin_org(request: Request, org_id: int) -> Organization:
    org = get_object_or_404(Organization, pk=org_id)
    require_org_admin(request.user, org, FeatureKey.LEADERSHIP)
    return org


def _viewer_member(user: CustomUser | AnonymousUser, org: Organization) -> OrgUser:
    if not user.is_authenticated:
        raise NotAuthenticated()
    member = OrgUser.objects.nocache().filter(organization=org, user_id=user.pk).first()
    if member is None:
        raise not_permitted()
    return member


@api_view(["GET", "PATCH"])
@parser_classes([JSONParser])
@permission_classes([AllowAny])
def leadership_settings(request: Request, org_id: int) -> Response:
    org = _admin_org(request, org_id)
    row = get_leadership_settings(org)
    if request.method == "PATCH":
        body = SettingsUpdateSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        changes = dict(body.validated_data)
        points = changes.pop("kind_points", None)
        try:
            row = update_leadership_settings(
                org, actor=request.user, changes=changes, points=points
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
    return Response({**settings_data(row), "kind_points": kind_points(org)})


@api_view(["GET", "PUT"])
@parser_classes([JSONParser])
@permission_classes([AllowAny])
def leadership_traits(request: Request, org_id: int) -> Response:
    if request.method == "PUT":
        org = _admin_org(request, org_id)
        body = TraitsPutSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        try:
            traits = upsert_traits(
                org, actor=request.user, items=body.validated_data["traits"]
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
    else:
        org = _org(org_id)
        if not has_org_admin_access(request.user, org):
            _viewer_member(request.user, org)
        traits = effective_traits(org)
    return Response({"traits": [trait_data(t) for t in traits]})


@api_view(["DELETE"])
@permission_classes([AllowAny])
def leadership_trait(request: Request, org_id: int, key: str) -> Response:
    org = _admin_org(request, org_id)
    try:
        delete_trait(org, actor=request.user, key=key)
    except CaptainTrait.DoesNotExist as exc:
        raise NotFound() from exc
    except TraitInUse as exc:
        raise Refused(
            ReviewRefused(
                "trait_in_use",
                "This trait has scores. Deactivate it instead.",
                status=409,
            )
        ) from exc
    except ValueError as exc:
        raise ValidationError({"detail": str(exc)}) from exc
    return Response(status=status.HTTP_204_NO_CONTENT)


def _snapshot_data(snapshot: EventCaptain) -> dict[str, Any]:
    return {
        "event_id": snapshot.event_id,
        "event_name": snapshot.event.name,
        "team_name": snapshot.team_name,
        "captain": member_summary(snapshot.captain),
        "window_closes_at": snapshot.window_closes_at,
    }


@api_view(["GET"])
@permission_classes([AllowAny])
def leadership_pending(request: Request, org_id: int) -> Response:
    org = _org(org_id)
    member = _viewer_member(request.user, org)
    now = timezone.now()
    snapshots = list(
        with_user_profiles(
            EventCaptain.objects.nocache()
            .filter(
                organization=org,
                voided_at__isnull=True,
                window_closes_at__gt=now,
                teammates=member,
            )
            .exclude(captain=member)
            .select_related("event"),
            "captain__user",
        ).order_by("window_closes_at", "pk")
    )
    own = {
        r.event_captain_id: r
        for r in CaptainReview.objects.nocache()
        .filter(event_captain__in=[s.pk for s in snapshots], rater=member)
        .prefetch_related(Prefetch("scores__trait"))
    }
    traits = effective_traits(org, active_only=True)
    items = []
    for snap in snapshots:
        review = own.get(snap.pk)
        items.append(
            {
                **_snapshot_data(snap),
                "review": (
                    {
                        "scores": {s.trait.key: s.score for s in review.scores.all()},
                        "submitted_at": review.submitted_at,
                        "void_kind": review.void_kind,
                    }
                    if review is not None
                    else None
                ),
            }
        )
    return Response({"traits": [trait_data(t) for t in traits], "pending": items})


@api_view(["PUT", "DELETE"])
@parser_classes([JSONParser])
@permission_classes([AllowAny])
@throttle_classes([CaptainReviewThrottle])
def leadership_review(
    request: Request, org_id: int, event_id: int, org_user_id: int
) -> Response:
    org = _org(org_id)
    rater = _viewer_member(request.user, org)
    get_object_or_404(Event.objects.nocache(), pk=event_id, organization=org)
    now = timezone.now()
    try:
        if request.method == "DELETE":
            withdraw_review(
                org_id=org.pk,
                event_id=event_id,
                captain_id=org_user_id,
                rater=rater,
                now=now,
            )
            return Response(status=status.HTTP_204_NO_CONTENT)
        body = ReviewPutSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        review = submit_review(
            org_id=org.pk,
            event_id=event_id,
            captain_id=org_user_id,
            rater=rater,
            scores=body.validated_data["scores"],
            now=now,
        )
    except ReviewRefused as exc:
        if exc.status == 404:
            raise NotFound() from exc
        raise Refused(exc) from exc
    return Response(
        {
            "scores": {
                s.trait.key: s.score for s in review.scores.select_related("trait")
            },
            "submitted_at": review.submitted_at,
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def leadership_member(request: Request, org_id: int, org_user_id: int) -> Response:
    org = _org(org_id)
    org_user = get_object_or_404(
        with_user_profiles(OrgUser.objects.filter(organization=org), "user"),
        pk=org_user_id,
    )
    user = request.user
    if not user.is_authenticated:
        raise NotAuthenticated()
    own = org_user.user_id == user.pk
    staff = has_org_admin_access(user, org)
    public = get_leadership_settings(org).leaderboard_public
    if not (own or staff or (public and can_view_org_members(user, org))):
        raise not_permitted()
    payload = member_payload(
        org_user,
        now=timezone.now(),
        detail=own or staff,
        staff=staff and not own,
    )
    return Response(payload)


def _review_data(review: CaptainReview) -> dict[str, Any]:
    return {
        "pk": review.pk,
        "captain": member_summary(review.event_captain.captain),
        "team_name": review.event_captain.team_name,
        "submitted_at": review.submitted_at,
        "voided_at": review.voided_at,
        "void_kind": review.void_kind,
        "void_reason": review.void_reason,
        "scores": {s.trait.key: s.score for s in review.scores.all()},
        "rater": member_summary(review.rater),
    }


@api_view(["GET"])
@permission_classes([AllowAny])
def leadership_event_reviews(request: Request, org_id: int, event_id: int) -> Response:
    org = _admin_org(request, org_id)
    event = get_object_or_404(Event.objects.nocache(), pk=event_id, organization=org)
    reviews = (
        with_user_profiles(
            with_user_profiles(
                CaptainReview.objects.nocache()
                .filter(event_captain__event=event, event_captain__organization=org)
                .exclude(event_captain__captain__user_id=request.user.pk),
                "rater__user",
            ),
            "event_captain__captain__user",
        )
        .select_related("event_captain")
        .prefetch_related("scores__trait")
        .order_by("event_captain__team_name", "pk")
    )
    return Response(
        {
            "event_id": event.pk,
            "reviews": [_review_data(r) for r in reviews],
        }
    )


def _moderate(
    request: Request, org_id: int, review_pk: int, *, unvoid: bool
) -> Response:
    org = _admin_org(request, org_id)
    body = ReasonSerializer(data=request.data)
    body.is_valid(raise_exception=True)
    action = unvoid_review if unvoid else void_review
    try:
        review = action(
            org_id=org.pk,
            review_pk=review_pk,
            actor=request.user,
            reason=body.validated_data["reason"],
            now=timezone.now(),
        )
    except ReviewRefused as exc:
        if exc.status == 404:
            raise NotFound() from exc
        raise Refused(exc) from exc
    return Response({"pk": review.pk, "void_kind": review.void_kind})


@api_view(["POST"])
@parser_classes([JSONParser])
@permission_classes([AllowAny])
def leadership_review_void(request: Request, org_id: int, review_pk: int) -> Response:
    return _moderate(request, org_id, review_pk, unvoid=False)


@api_view(["POST"])
@parser_classes([JSONParser])
@permission_classes([AllowAny])
def leadership_review_unvoid(request: Request, org_id: int, review_pk: int) -> Response:
    return _moderate(request, org_id, review_pk, unvoid=True)
