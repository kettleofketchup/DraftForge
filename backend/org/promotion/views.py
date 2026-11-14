from django.contrib.auth.models import AnonymousUser
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.decorators import api_view, parser_classes, permission_classes
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from app.models import CustomUser, Organization
from app.permissions_org import has_org_staff_access
from events.models import Event
from org.feature_errors import not_permitted, require_org_staff, require_promoter
from org.features import FeatureKey, org_has_feature
from org.models import ContributionEntry, PromoSend, PromoTemplate
from org.promotion.recipients import CandidateRow, candidates, clamp_pool_n
from org.promotion.render import (
    PLACEHOLDERS,
    build_context,
    render_template,
    validate_template_body,
)
from org.promotion.serializers import (
    CandidatesQuerySerializer,
    PromoEventSerializer,
    PromoTemplateSerializer,
    RenderRequestSerializer,
    SendRequestSerializer,
    send_data,
)
from org.promotion.services import (
    PROMOTABLE_STATES,
    PromoSendError,
    can_undo,
    record_promo_send,
    undo_promo_send,
    validate_send_target,
    will_earn,
)
from telemetry.logging import get_logger

log = get_logger(__name__)


def _promoter_org(request: Request, org_id: int) -> Organization:
    org = get_object_or_404(Organization, pk=org_id)
    require_promoter(request.user, org)
    return org


def _staff_org(request: Request, org_id: int) -> Organization:
    org = get_object_or_404(Organization, pk=org_id)
    require_org_staff(request.user, org, FeatureKey.PROMOTION)
    return org


def _event(org: Organization, event_id: int) -> Event:
    return get_object_or_404(
        Event.objects.nocache().select_related("organization"),
        pk=event_id,
        organization=org,
    )


def _template(org: Organization, template_id: int) -> PromoTemplate:
    return get_object_or_404(
        PromoTemplate.objects.nocache(), pk=template_id, organization=org
    )


def _recipient(recipient_id: int) -> CustomUser:
    recipient = CustomUser.objects.filter(pk=recipient_id).first()
    if recipient is None:
        raise ValidationError({"recipient_id": ["user not found"]})
    return recipient


def _template_response(template: PromoTemplate, status_code: int) -> Response:
    data = PromoTemplateSerializer(template).data
    data["warnings"] = validate_template_body(template.body)
    return Response(data, status=status_code)


@api_view(["GET"])
@permission_classes([AllowAny])
def promotion_placeholders(request: Request, org_id: int) -> Response:
    _promoter_org(request, org_id)
    return Response(list(PLACEHOLDERS))


def _create_template(request: Request, org: Organization) -> Response:
    body = PromoTemplateSerializer(data=request.data)
    body.is_valid(raise_exception=True)
    template = body.save(organization=org, created_by=request.user)
    log.info(
        "promo_template_created",
        system="org",
        subsystem="promotion",
        org_id=org.pk,
        template_id=template.pk,
        actor_id=request.user.pk,
    )
    return _template_response(template, status.HTTP_201_CREATED)


@api_view(["GET", "POST"])
@parser_classes([JSONParser])
@permission_classes([AllowAny])
def promotion_templates(request: Request, org_id: int) -> Response:
    if request.method == "POST":
        return _create_template(request, _staff_org(request, org_id))
    org = _promoter_org(request, org_id)
    templates = PromoTemplate.objects.nocache().filter(organization=org)
    return Response(PromoTemplateSerializer(templates, many=True).data)


@api_view(["PATCH", "DELETE"])
@parser_classes([JSONParser])
@permission_classes([AllowAny])
def promotion_template(request: Request, org_id: int, template_pk: int) -> Response:
    org = _staff_org(request, org_id)
    template = _template(org, template_pk)
    if request.method == "DELETE":
        template.delete()
        log.info(
            "promo_template_deleted",
            system="org",
            subsystem="promotion",
            org_id=org.pk,
            template_id=template_pk,
            actor_id=request.user.pk,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)
    body = PromoTemplateSerializer(template, data=request.data, partial=True)
    body.is_valid(raise_exception=True)
    template = body.save()
    log.info(
        "promo_template_updated",
        system="org",
        subsystem="promotion",
        org_id=org.pk,
        template_id=template.pk,
        actor_id=request.user.pk,
    )
    return _template_response(template, status.HTTP_200_OK)


@api_view(["GET"])
@permission_classes([AllowAny])
def promotion_events(request: Request, org_id: int) -> Response:
    org = _promoter_org(request, org_id)
    events = (
        Event.objects.nocache()
        .filter(organization=org, state__in=PROMOTABLE_STATES)
        .order_by("scheduled_at", "pk")
    )
    return Response(PromoEventSerializer(events, many=True).data)


def _fill_can_undo(
    rows: list[CandidateRow], user: CustomUser | AnonymousUser, org: Organization
) -> None:
    send_ids = [r["last_messaged"]["send_id"] for r in rows if r["last_messaged"]]
    if not send_ids:
        return
    if has_org_staff_access(user, org):
        allowed = set(send_ids)
    else:
        allowed = set(
            PromoSend.objects.filter(pk__in=send_ids, sender_id=user.pk).values_list(
                "pk", flat=True
            )
        )
    for row in rows:
        last = row["last_messaged"]
        if last is not None:
            last["can_undo"] = last["send_id"] in allowed


@api_view(["GET"])
@permission_classes([AllowAny])
def promotion_candidates(request: Request, org_id: int, event_id: int) -> Response:
    org = _promoter_org(request, org_id)
    event = _event(org, event_id)
    query = CandidatesQuerySerializer(data=request.query_params.dict())
    query.is_valid(raise_exception=True)
    params = query.validated_data
    n = clamp_pool_n(params.get("n") or None)
    rows = candidates(
        org,
        event,
        n=n,
        sender=request.user,
        hide_signed_up=params["hide_signed_up"],
        hide_messaged=params["hide_messaged"],
        q=params["q"],
    )
    _fill_can_undo(rows, request.user, org)
    return Response({"n": n, "rows": rows})


@api_view(["POST"])
@parser_classes([JSONParser])
@permission_classes([AllowAny])
def promotion_render(request: Request, org_id: int, event_id: int) -> Response:
    org = _promoter_org(request, org_id)
    event = _event(org, event_id)
    body = RenderRequestSerializer(data=request.data)
    body.is_valid(raise_exception=True)
    template = _template(org, body.validated_data["template_id"])
    recipient = _recipient(body.validated_data["recipient_id"])
    try:
        validate_send_target(
            sender=request.user, event=event, recipient=recipient, template=template
        )
    except PromoSendError as exc:
        raise ValidationError({exc.field: [str(exc)]}) from exc
    context = build_context(
        event=event, recipient=recipient, sender=request.user, org=org
    )
    result = render_template(template.body, context)
    return Response(
        {
            "text": result.text,
            "warnings": result.warnings,
            "will_earn": will_earn(request.user, event, recipient),
        }
    )


@api_view(["POST"])
@parser_classes([JSONParser])
@permission_classes([AllowAny])
def promotion_sends(request: Request, org_id: int, event_id: int) -> Response:
    org = _promoter_org(request, org_id)
    event = _event(org, event_id)
    body = SendRequestSerializer(data=request.data)
    body.is_valid(raise_exception=True)
    data = body.validated_data
    template_id = data.get("template_id")
    template = _template(org, template_id) if template_id is not None else None
    recipient = _recipient(data["recipient_id"])
    try:
        send = record_promo_send(
            sender=request.user,
            event=event,
            recipient=recipient,
            template=template,
            text=data["text"],
        )
    except PromoSendError as exc:
        raise ValidationError({exc.field: [str(exc)]}) from exc
    points = (
        ContributionEntry.objects.nocache()
        .filter(promo_send=send)
        .values_list("points", flat=True)
        .first()
        if send.earns_points and org_has_feature(org, FeatureKey.CONTRIBUTIONS)
        else None
    )
    return Response(send_data(send, points), status=status.HTTP_201_CREATED)


@api_view(["DELETE"])
@permission_classes([AllowAny])
def promotion_send(request: Request, org_id: int, send_pk: int) -> Response:
    org = _promoter_org(request, org_id)
    send = get_object_or_404(
        PromoSend.objects.select_related("organization", "event"),
        pk=send_pk,
        organization=org,
    )
    if not can_undo(request.user, send):
        raise not_permitted()
    undo_promo_send(send, actor=request.user)
    return Response(status=status.HTTP_204_NO_CONTENT)
