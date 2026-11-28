"""Field-level subscriptions for messages whose layouts depend on Django rows."""

from collections.abc import Callable, Iterable
from typing import Any

from django.db.models import Model
from django.db.models.signals import post_delete, post_save, pre_save
from django.dispatch import receiver

from discordbot.live_messages import invalidate_live_messages, invalidate_live_subjects
from events.live_signals import event_data_changed
from events.models import Event, EventSignup
from org.models import Organization

REMINDER = "event_signup_reminder"


def watch_live_fields[T: Model](
    model: type[T],
    *,
    renderer: str,
    fields: set[str],
    subject_ids: Callable[[T], Iterable[int]],
    on_create: bool = True,
    saved_subject_ids: Callable[[T], Iterable[int]] | None = None,
) -> None:
    """Refresh subjects on matching saves and deletes, inside the caller's transaction.

    A resolver can return a queryset to refresh multiple subjects in a single SQL
    statement. Full saves have no changed-field list, so the renderer's digest is
    the final check before issuing an edit.
    """

    def saved(
        *,
        instance: T,
        raw: bool,
        created: bool,
        update_fields: frozenset[str] | None,
        **kwargs: Any,
    ) -> None:
        if raw or (created and not on_create):
            return
        if update_fields is None or not fields.isdisjoint(update_fields):
            invalidate_live_subjects(
                renderer, (saved_subject_ids or subject_ids)(instance)
            )

    def deleted(*, instance: T, **kwargs: Any) -> None:
        invalidate_live_subjects(renderer, subject_ids(instance))

    uid = f"live.{renderer}.{model._meta.label_lower}"
    post_save.connect(saved, model, weak=False, dispatch_uid=uid)
    post_delete.connect(deleted, model, weak=False, dispatch_uid=uid)


@receiver(pre_save, sender=EventSignup, dispatch_uid="live.signup.previous_event")
def signup_leaving_event(
    *,
    instance: EventSignup,
    raw: bool,
    update_fields: frozenset[str] | None,
    **kwargs: Any,
) -> None:
    if raw or instance.pk is None:
        return
    if update_fields is not None and {"event", "event_id"}.isdisjoint(update_fields):
        return
    previous = (
        EventSignup.objects.nocache()
        .filter(pk=instance.pk)
        .values_list("event_id", flat=True)
        .first()
    )
    if previous is not None and previous != instance.event_id:
        invalidate_live_messages(REMINDER, previous)


@receiver(
    event_data_changed, sender=Event, dispatch_uid="live.signup.event_data_changed"
)
def event_changed(*, event_id: int, **kwargs: Any) -> None:
    invalidate_live_messages(REMINDER, event_id)


def connect_live_signals() -> None:
    watch_live_fields(
        Event,
        renderer=REMINDER,
        fields={
            "name",
            "description",
            "scheduled_at",
            "timezone",
            "max_players",
            "state",
            "allow_user_signups",
            "organization",
            "organization_id",
        },
        subject_ids=lambda event: (event.pk,),
        on_create=False,
    )
    watch_live_fields(
        EventSignup,
        renderer=REMINDER,
        fields={"event", "event_id", "status"},
        subject_ids=lambda signup: (signup.event_id,),
        # A partial save can leave an unsaved FK assignment on the instance.
        saved_subject_ids=lambda signup: EventSignup.objects.filter(
            pk=signup.pk
        ).values_list("event_id", flat=True),
    )
    watch_live_fields(
        Organization,
        renderer=REMINDER,
        fields={"name", "logo"},
        subject_ids=lambda org: Event.objects.filter(
            organization_id=org.pk
        ).values_list("pk", flat=True),
        on_create=False,
    )
