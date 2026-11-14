from typing import Final

from django.contrib.auth.models import AnonymousUser
from django.db import transaction

from app.models import CustomUser
from app.permissions_org import (
    has_org_promoter_access,
    has_org_staff_access,
    is_org_role_holder,
)
from events.constants import EventState
from events.models import Event
from org.contributions.kinds import ContributionKind
from org.contributions.services import award_entry
from org.models import ContributionEntry, PromoSend, PromoTemplate
from org.promotion.recipients import in_pool
from telemetry.logging import get_logger

log = get_logger(__name__)

PROMOTABLE_STATES: Final[tuple[EventState, ...]] = (
    EventState.UPCOMING,
    EventState.SIGNUPS_OPEN,
)
MAX_SEND_TEXT: Final[int] = 4000


class PromoSendError(ValueError):
    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


def _earning_send_exists(event: Event, recipient: CustomUser) -> bool:
    return PromoSend.objects.filter(
        event=event, recipient=recipient, earns_points=True
    ).exists()


def will_earn(sender: CustomUser, event: Event, recipient: CustomUser) -> bool:
    return is_org_role_holder(
        sender, event.organization_id
    ) and not _earning_send_exists(event, recipient)


def _lock_event(event: Event) -> Event:
    return (
        Event.objects.nocache()
        .select_for_update()
        .select_related("organization")
        .get(pk=event.pk)
    )


def _validate_send(
    *,
    sender: CustomUser,
    event: Event,
    recipient: CustomUser,
    template: PromoTemplate | None,
    text: str,
) -> None:
    if event.state not in PROMOTABLE_STATES:
        raise PromoSendError("event", "event is not open for promotion")
    if template is not None and template.organization_id != event.organization_id:
        raise PromoSendError("template_id", "template belongs to another organization")
    if not recipient.discordId:
        raise PromoSendError("recipient_id", "recipient has no Discord account linked")
    if recipient.pk == sender.pk:
        raise PromoSendError("recipient_id", "you cannot promote to yourself")
    if not in_pool(event.organization, event, recipient):
        raise PromoSendError(
            "recipient_id", "recipient is not in this event's player pool"
        )
    if len(text) > MAX_SEND_TEXT:
        raise PromoSendError(
            "text", f"message must be at most {MAX_SEND_TEXT} characters"
        )


def _award_send(send: PromoSend, event: Event, sender: CustomUser) -> None:
    award_entry(
        org=event.organization,
        user=sender,
        kind=ContributionKind.PROMO_MESSAGE,
        occurred_at=send.sent_at,
        event=event,
        promo_send=send,
    )


@transaction.atomic
def record_promo_send(
    *,
    sender: CustomUser,
    event: Event,
    recipient: CustomUser,
    template: PromoTemplate | None,
    text: str,
) -> PromoSend:
    event = _lock_event(event)
    _validate_send(
        sender=sender, event=event, recipient=recipient, template=template, text=text
    )
    earns = will_earn(sender, event, recipient)
    send = PromoSend.objects.create(
        organization=event.organization,
        event=event,
        recipient=recipient,
        sender=sender,
        template=template,
        text=text,
        earns_points=earns,
    )
    if earns:
        _award_send(send, event, sender)
    log.info(
        "promo_send_recorded",
        system="org",
        subsystem="promotion",
        org_id=event.organization_id,
        event_id=event.pk,
        send_id=send.pk,
        sender_id=sender.pk,
        recipient_id=recipient.pk,
        template_id=template.pk if template is not None else None,
        earns_points=earns,
    )
    return send


@transaction.atomic
def undo_promo_send(send: PromoSend, *, actor: CustomUser | None) -> None:
    event = _lock_event(send.event)
    send = PromoSend.objects.select_for_update().get(pk=send.pk)
    was_earning = send.earns_points
    send_id = send.pk
    recipient_id = send.recipient_id
    ContributionEntry.objects.nocache().filter(promo_send=send).delete()
    send.delete()

    promoted: PromoSend | None = None
    if was_earning and recipient_id is not None:
        remaining = (
            PromoSend.objects.filter(
                event=event, recipient_id=recipient_id, sender__isnull=False
            )
            .select_related("sender")
            .order_by("sent_at", "pk")
        )
        for candidate in remaining:
            if is_org_role_holder(candidate.sender, event.organization_id):
                promoted = candidate
                break
        if promoted is not None:
            promoted.earns_points = True
            promoted.save(update_fields=["earns_points"])
            _award_send(promoted, event, promoted.sender)

    log.info(
        "promo_send_undone",
        system="org",
        subsystem="promotion",
        org_id=event.organization_id,
        event_id=event.pk,
        send_id=send_id,
        recipient_id=recipient_id,
        actor_id=actor.pk if actor is not None else None,
        was_earning=was_earning,
        promoted_send_id=promoted.pk if promoted is not None else None,
    )


def can_undo(user: CustomUser | AnonymousUser, send: PromoSend) -> bool:
    if not user.is_authenticated:
        return False
    if send.sender_id == user.pk and has_org_promoter_access(
        user, send.organization_id
    ):
        return True
    return has_org_staff_access(user, send.organization)
