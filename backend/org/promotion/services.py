from typing import Final

from django.contrib.auth.models import AnonymousUser
from django.db import transaction

from app.models import CustomUser
from events.constants import EventState
from events.models import Event
from org.contributions.kinds import ContributionKind
from org.contributions.services import (
    award_entry,
    has_promo_entry,
    revoke_promo_entry,
)
from org.integration.event_lock import with_event_mutation
from org.integration.outbox import enqueue_send
from org.integration.ticks import external_contact_for
from org.models import PromoSend, PromoTemplate
from org.permissions import (
    has_org_promoter_access,
    has_org_staff_access,
    is_org_role_holder,
)
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


class ContactAlreadyRecorded(PromoSendError):
    """An external contact for this recipient and event is recorded."""

    code: Final[str] = "contact_already_recorded"

    def __init__(self) -> None:
        super().__init__(
            "recipient_id", "a contact with this player is already recorded externally"
        )


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


def validate_send_target(
    *,
    sender: CustomUser,
    event: Event,
    recipient: CustomUser,
    template: PromoTemplate | None,
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


def _validate_send(
    *,
    sender: CustomUser,
    event: Event,
    recipient: CustomUser,
    template: PromoTemplate | None,
    text: str,
) -> None:
    validate_send_target(
        sender=sender, event=event, recipient=recipient, template=template
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


def record_promo_send(
    *,
    sender: CustomUser,
    event: Event,
    recipient: CustomUser,
    template: PromoTemplate | None,
    text: str,
) -> PromoSend:
    """Record one manual promotion DM, its outbox receipt and any award.

    Runs under the event's mutation lock, the same one an external contact
    import takes, so a recipient whose external contact has committed can
    no longer be sent to (``ContactAlreadyRecorded``).
    """
    return with_event_mutation(
        event.pk,
        lambda: _record_locked(
            sender=sender,
            event_id=event.pk,
            recipient=recipient,
            template=template,
            text=text,
        ),
    )


def _discord_snapshot(discord_id: str | None) -> str:
    """The recipient's Discord ID as stored on the send, or "" if unusable."""
    if discord_id and len(discord_id) <= 20:
        return discord_id
    return ""


def _record_locked(
    *,
    sender: CustomUser,
    event_id: int,
    recipient: CustomUser,
    template: PromoTemplate | None,
    text: str,
) -> PromoSend:
    event = Event.objects.nocache().select_related("organization").get(pk=event_id)
    _validate_send(
        sender=sender, event=event, recipient=recipient, template=template, text=text
    )
    if recipient.discordId and (
        external_contact_for(event.pk, recipient.discordId, user_id=recipient.pk)
        is not None
    ):
        raise ContactAlreadyRecorded()
    earns = will_earn(sender, event, recipient)
    send = PromoSend.objects.create(
        organization=event.organization,
        event=event,
        recipient=recipient,
        recipient_discord_id=_discord_snapshot(recipient.discordId),
        sender=sender,
        template=template,
        text=text,
        earns_points=earns,
    )
    enqueue_send(send)
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


def _promote_next_send(
    event: Event, recipient_id: int, *, exclude_sender_id: int | None = None
) -> PromoSend | None:
    remaining = (
        PromoSend.objects.filter(
            event=event,
            recipient_id=recipient_id,
            sender__isnull=False,
            earns_points=False,
        )
        .select_related("sender")
        .order_by("sent_at", "pk")
    )
    if exclude_sender_id is not None:
        remaining = remaining.exclude(sender_id=exclude_sender_id)
    promoted = next(
        (
            candidate
            for candidate in remaining
            if is_org_role_holder(candidate.sender, event.organization_id)
        ),
        None,
    )
    if promoted is None:
        return None
    promoted.earns_points = True
    promoted.save(update_fields=["earns_points"])
    if not has_promo_entry(promoted):
        _award_send(promoted, event, promoted.sender)
    return promoted


@transaction.atomic
def release_earning_sends(user: CustomUser) -> int:
    event_ids = sorted(
        set(
            PromoSend.objects.filter(sender=user, earns_points=True).values_list(
                "event_id", flat=True
            )
        )
    )
    released = 0
    for event_id in event_ids:
        event = _lock_event(Event(pk=event_id))
        sends = list(
            PromoSend.objects.select_for_update().filter(
                event=event, sender=user, earns_points=True
            )
        )
        for send in sends:
            send.earns_points = False
            send.save(update_fields=["earns_points"])
            if send.recipient_id is not None:
                _promote_next_send(event, send.recipient_id, exclude_sender_id=user.pk)
            released += 1
    if released:
        log.info(
            "promo_sends_released_for_deleted_sender",
            system="org",
            subsystem="promotion",
            user_id=user.pk,
            released=released,
        )
    return released


@transaction.atomic
def undo_promo_send(send: PromoSend, *, actor: CustomUser | None) -> None:
    event = _lock_event(send.event)
    locked = PromoSend.objects.select_for_update().filter(pk=send.pk).first()
    if locked is None:
        return
    send = locked
    was_earning = send.earns_points
    send_id = send.pk
    recipient_id = send.recipient_id
    revoke_promo_entry(send)
    send.delete()

    promoted: PromoSend | None = None
    if was_earning and recipient_id is not None:
        promoted = _promote_next_send(event, recipient_id)

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


def demote_colliding_earning_sends(keep: CustomUser, drop: CustomUser) -> int:
    keep_events = PromoSend.objects.filter(recipient=keep, earns_points=True).values(
        "event_id"
    )
    demoted = PromoSend.objects.filter(
        recipient=drop, earns_points=True, event_id__in=keep_events
    ).update(earns_points=False)
    if demoted:
        log.info(
            "promo_sends_demoted_for_merge",
            system="org",
            subsystem="promotion",
            keep_user_id=keep.pk,
            drop_user_id=drop.pk,
            demoted=demoted,
        )
    return demoted
