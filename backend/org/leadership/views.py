from collections import defaultdict
from datetime import datetime
from typing import Any

from django.contrib.auth.models import AnonymousUser
from django.db.models import Prefetch, QuerySet
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
from org.feature_errors import (
    not_permitted,
    require_feature,
    require_org_admin,
    require_org_staff,
)
from org.features import FeatureKey
from org.leadership.queries import EventAggregate, captain_events
from org.leadership.release import (
    annotate_live,
    auto_release_at,
    release_floor,
    release_state,
)
from org.leadership.reviews import (
    ReviewRefused,
    release_results,
    submit_review,
    unvoid_review,
    void_review,
    withdraw_review,
)
from org.leadership.serializers import (
    ReasonSerializer,
    ReleaseBodySerializer,
    ReviewPutSerializer,
    SettingsUpdateSerializer,
    TraitsPutSerializer,
    settings_data,
)
from org.leadership.settings import (
    get_leadership_settings,
    kind_points,
    moderator_count,
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
from org.models_leadership import (
    CaptainReview,
    CaptainTrait,
    CaptainTraitScore,
    EventCaptain,
    OrgLeadershipSettings,
)
from org.permissions import can_view_org_members, has_org_staff_access
from user.querysets import with_user_profiles


class CaptainReviewThrottle(UserRateThrottle):
    scope = "captain_review"
    rate = "30/min"


class Refused(APIException):
    def __init__(self, exc: ReviewRefused) -> None:
        super().__init__(detail={"code": exc.code, "detail": exc.detail})
        self.status_code = exc.status


def _refused(exc: ReviewRefused) -> APIException:
    return NotFound() if exc.status == 404 else Refused(exc)


def _org(org_id: int) -> Organization:
    org = get_object_or_404(Organization, pk=org_id)
    require_feature(org, FeatureKey.LEADERSHIP)
    return org


def _admin_org(request: Request, org_id: int) -> Organization:
    org = get_object_or_404(Organization, pk=org_id)
    require_org_admin(request.user, org, FeatureKey.LEADERSHIP)
    return org


def _moderator_org(request: Request, org_id: int) -> Organization:
    org = get_object_or_404(Organization, pk=org_id)
    require_org_staff(request.user, org, FeatureKey.LEADERSHIP)
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
        points = changes.pop("points", None)
        try:
            row = update_leadership_settings(
                org, actor=request.user, changes=changes, points=points
            )
        except ValueError as exc:
            raise ValidationError({"detail": str(exc)}) from exc
        except ReviewRefused as exc:
            raise _refused(exc) from exc
    return Response(
        settings_data(row, kind_points(org), moderator_count=moderator_count(org))
    )


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
        if not has_org_staff_access(request.user, org):
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
        raise _refused(
            ReviewRefused(
                "trait_in_use", 409, "This trait has scores. Deactivate it instead."
            )
        ) from exc
    except ValueError as exc:
        raise ValidationError({"detail": str(exc)}) from exc
    return Response(status=status.HTTP_204_NO_CONTENT)


def _scores(review: CaptainReview) -> dict[str, int]:
    return {s.trait.key: s.score for s in review.scores.all()}


def _snapshot_data(snapshot: EventCaptain) -> dict[str, Any]:
    return {
        "event_id": snapshot.event_id,
        "event_name": snapshot.event.name,
        "captain_org_user_id": snapshot.captain_id,
        "captain": member_summary(snapshot.captain),
        "team_name": snapshot.team_name,
        "window_closes_at": snapshot.window_closes_at,
    }


def _event_filter(request: Request) -> int | None:
    raw = request.query_params.get("event_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ValidationError({"event_id": ["Must be an integer."]}) from exc


def _own_reviews(member: OrgUser) -> QuerySet[CaptainReview]:
    return (
        CaptainReview.objects.nocache()
        .filter(rater=member)
        .prefetch_related(
            Prefetch(
                "scores",
                queryset=CaptainTraitScore.objects.nocache().select_related("trait"),
            )
        )
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def leadership_pending(request: Request, org_id: int) -> Response:
    org = _org(org_id)
    member = _viewer_member(request.user, org)
    event_id = _event_filter(request)
    snapshots = (
        EventCaptain.objects.nocache()
        .filter(
            organization=org,
            voided_at__isnull=True,
            window_closes_at__gt=timezone.now(),
            teammates=member,
        )
        .exclude(captain=member)
        .select_related("event")
    )
    if event_id is not None:
        snapshots = snapshots.filter(event_id=event_id)
    found = list(
        with_user_profiles(snapshots, "captain__user").order_by(
            "window_closes_at", "pk"
        )
    )
    own = {
        r.event_captain_id: r
        for r in _own_reviews(member).filter(event_captain__in=[s.pk for s in found])
    }
    traits = [
        {"key": t.key, "label": t.label}
        for t in effective_traits(org, active_only=True)
    ]
    items = []
    for snap in found:
        review = own.get(snap.pk)
        items.append(
            {
                **_snapshot_data(snap),
                "traits": traits,
                "scores": _scores(review) if review is not None else None,
                "void_kind": review.void_kind if review is not None else "",
            }
        )
    return Response(items)


@api_view(["GET"])
@permission_classes([AllowAny])
def leadership_mine(request: Request, org_id: int) -> Response:
    org = _org(org_id)
    member = _viewer_member(request.user, org)
    reviews = with_user_profiles(
        _own_reviews(member)
        .filter(event_captain__organization=org)
        .select_related("event_captain__event"),
        "event_captain__captain__user",
    ).order_by("-event_captain__event__scheduled_at", "pk")
    return Response(
        [
            {
                **_snapshot_data(r.event_captain),
                "scores": _scores(r),
                "submitted_at": r.submitted_at,
                "updated_at": r.updated_at,
                "void_kind": r.void_kind,
            }
            for r in reviews
        ]
    )


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
                org,
                event_id=event_id,
                captain_org_user_id=org_user_id,
                rater=rater,
                now=now,
            )
            return Response(status=status.HTTP_204_NO_CONTENT)
        body = ReviewPutSerializer(data=request.data)
        body.is_valid(raise_exception=True)
        review = submit_review(
            org,
            event_id=event_id,
            captain_org_user_id=org_user_id,
            rater=rater,
            scores=body.validated_data["scores"],
            now=now,
        )
    except ReviewRefused as exc:
        raise _refused(exc) from exc
    return Response(
        {
            "scores": {
                s.trait.key: s.score for s in review.scores.select_related("trait")
            },
            "submitted_at": review.submitted_at,
            "updated_at": review.updated_at,
        }
    )


@api_view(["GET"])
@permission_classes([AllowAny])
def leadership_member(request: Request, org_id: int, org_user_id: int) -> Response:
    org = _org(org_id)
    user = request.user
    if not user.is_authenticated:
        raise NotAuthenticated()
    org_user = get_object_or_404(
        with_user_profiles(OrgUser.objects.filter(organization=org), "user"),
        pk=org_user_id,
    )
    own = org_user.user_id == user.pk
    staff = has_org_staff_access(user, org)
    if not (own or staff):
        public = get_leadership_settings(org).leaderboard_public
        if not (public and can_view_org_members(user, org)):
            raise not_permitted()
    payload = member_payload(
        org_user,
        now=timezone.now(),
        detail=own or staff,
        staff=staff and not own,
        viewer_user_id=user.pk,
        period_points=True,
    )
    return Response(payload)


def _review_data(review: CaptainReview) -> dict[str, Any]:
    return {
        "pk": review.pk,
        "rater": member_summary(review.rater) if review.rater else None,
        "scores": _scores(review),
        "submitted_at": review.submitted_at,
        "updated_at": review.updated_at,
        "voided_at": review.voided_at,
        "void_kind": review.void_kind,
        "void_reason": review.void_reason,
    }


def _review_rows(reviews: QuerySet[CaptainReview]) -> QuerySet[CaptainReview]:
    return with_user_profiles(reviews, "rater__user").prefetch_related(
        Prefetch(
            "scores",
            queryset=CaptainTraitScore.objects.nocache().select_related("trait"),
        )
    )


def _own_aggregate(
    org: Organization,
    snapshot: EventCaptain,
    *,
    now: datetime,
    settings: OrgLeadershipSettings,
) -> EventAggregate | None:
    rows = captain_events(
        snapshot.captain,
        now=now,
        settings=settings,
        traits=effective_traits(org),
        staff=False,
    )
    return next((r for r in rows if r["event_id"] == snapshot.event_id), None)


def _released_by(snap: EventCaptain) -> dict[str, Any] | None:
    user = snap.released_by
    return None if user is None else {"pk": user.pk, "username": user.username}


def _release_fields(
    snap: EventCaptain,
    *,
    own: bool,
    floor: int,
    settings: OrgLeadershipSettings,
    now: datetime,
) -> dict[str, Any]:
    state = release_state(snap, live=snap.live, settings=settings, now=now)
    released = state == "released"
    if own:
        return {
            "released": released,
            "release_state": "released" if released else "hidden",
            "released_at": snap.released_at if released else None,
            "released_by": _released_by(snap) if released else None,
            "auto_release_at": None,
            "live_reviews": None,
            "release_floor": None,
            "can_release": False,
        }
    pending = state == "pending"
    return {
        "released": released,
        "release_state": state,
        "released_at": snap.released_at,
        "released_by": _released_by(snap),
        "auto_release_at": auto_release_at(snap, settings) if pending else None,
        "live_reviews": snap.live,
        "release_floor": floor,
        "can_release": pending,
    }


@api_view(["GET"])
@permission_classes([AllowAny])
def leadership_event_reviews(request: Request, org_id: int, event_id: int) -> Response:
    org = _moderator_org(request, org_id)
    event = get_object_or_404(Event.objects.nocache(), pk=event_id, organization=org)
    now = timezone.now()
    settings = get_leadership_settings(org)
    floor = release_floor(settings.rating_min_reviewers)
    snapshots = list(
        annotate_live(
            with_user_profiles(
                EventCaptain.objects.nocache()
                .filter(event=event, organization=org)
                .select_related("released_by"),
                "captain__user",
            )
        ).order_by("team_name", "pk")
    )
    others = [s.pk for s in snapshots if s.captain.user_id != request.user.pk]
    by_snapshot: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    if others:
        for review in _review_rows(
            CaptainReview.objects.nocache().filter(event_captain__in=others)
        ).order_by("submitted_at", "pk"):
            by_snapshot[review.event_captain_id].append(_review_data(review))
    captains = []
    for snap in snapshots:
        own = snap.captain.user_id == request.user.pk
        aggregate = (
            _own_aggregate(org, snap, now=now, settings=settings) if own else None
        )
        captains.append(
            {
                "org_user_id": snap.captain_id,
                "captain": member_summary(snap.captain),
                "team_name": snap.team_name,
                "window_closes_at": snap.window_closes_at,
                "voided_at": snap.voided_at,
                **_release_fields(
                    snap, own=own, floor=floor, settings=settings, now=now
                ),
                "own_snapshot": own,
                "reviews": None if own else by_snapshot[snap.pk],
                "aggregate": aggregate,
            }
        )
    return Response(
        {
            "event": {"pk": event.pk, "name": event.name},
            "require_staff_release": settings.require_staff_release,
            "captains": captains,
        }
    )


@api_view(["POST"])
@parser_classes([JSONParser])
@permission_classes([AllowAny])
def leadership_event_release(request: Request, org_id: int, event_id: int) -> Response:
    org = _moderator_org(request, org_id)
    event = get_object_or_404(Event.objects.nocache(), pk=event_id, organization=org)
    body = ReleaseBodySerializer(data=request.data)
    body.is_valid(raise_exception=True)
    try:
        result = release_results(
            org,
            event=event,
            actor=request.user,
            captain_ids=body.validated_data.get("captains"),
            now=timezone.now(),
        )
    except ReviewRefused as exc:
        raise _refused(exc) from exc
    return Response({"released": result.released, "skipped": result.skipped})


def _moderate(
    request: Request, org_id: int, review_pk: int, *, unvoid: bool
) -> Response:
    org = _moderator_org(request, org_id)
    try:
        if unvoid:
            review = unvoid_review(
                org, review_id=review_pk, actor=request.user, now=timezone.now()
            )
        else:
            body = ReasonSerializer(data=request.data)
            body.is_valid(raise_exception=True)
            review = void_review(
                org,
                review_id=review_pk,
                actor=request.user,
                reason=body.validated_data["reason"],
                now=timezone.now(),
            )
    except ReviewRefused as exc:
        raise _refused(exc) from exc
    row = _review_rows(CaptainReview.objects.nocache().filter(pk=review.pk)).get()
    return Response(_review_data(row))


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
