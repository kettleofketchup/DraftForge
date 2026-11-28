"""Field-level subscriptions for messages whose layouts depend on Django rows."""

from collections.abc import Callable, Iterable
from typing import Any

from django.db.models import Model, QuerySet
from django.db.models.signals import post_save, pre_delete, pre_save
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

    Resolve subjects before the row is deleted and after it is saved. A resolver
    can return a queryset to refresh multiple subjects in a single SQL statement.
    Full saves have no changed-field list, so the renderer's digest is the final
    check before issuing an edit.
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

    def deleting(*, instance: T, **kwargs: Any) -> None:
        invalidate_live_subjects(renderer, subject_ids(instance))

    uid = f"live.{renderer}.{model._meta.label_lower}"
    post_save.connect(saved, model, weak=False, dispatch_uid=uid)
    pre_delete.connect(deleting, model, weak=False, dispatch_uid=uid)


def _signup_event_ids(signup: EventSignup) -> QuerySet[EventSignup, int]:
    return (
        EventSignup.objects.using(signup._state.db)
        .nocache()
        .filter(pk=signup.pk)
        .values_list("event_id", flat=True)
    )


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
    previous = _signup_event_ids(instance).select_for_update().first()
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
        # Hold the persisted signup parent stable until the delete commits.
        subject_ids=lambda signup: list(_signup_event_ids(signup).select_for_update()),
        saved_subject_ids=_signup_event_ids,
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
