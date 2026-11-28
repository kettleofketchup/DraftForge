"""Leadership review DMs: planning sends and button clicks."""

from collections.abc import Mapping, Sequence
from datetime import datetime, timedelta
from typing import Any, Final

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Prefetch
from django.utils import timezone

from discordbot import dm_ledger
from discordbot.models import DMStatus
from discordbot.schemas import ClickResult, PlannedMessage
from org.feature_keys import FeatureKey
from org.features import org_has_feature
from org.leadership.errors import ReviewRefused
from org.leadership.review_dm_render import (
    MAX_TRAITS_PER_MESSAGE,
    StatusState,
    TraitRow,
    render_part,
)
from org.leadership.reviews import check_rater_writable, submit_review
from org.leadership.settings import get_leadership_settings
from org.leadership.traits import effective_traits, materialize_traits
from org.models import OrgUser
from org.models_leadership import (
    CaptainReview,
    CaptainReviewDraft,
    CaptainTrait,
    CaptainTraitScore,
    EventCaptain,
)
from telemetry.logging import get_logger
from user.display_names import user_display_name

log = get_logger(__name__)

OUT_OF_DATE: Final[str] = "This review message is out of date. Review on the site."
NOT_YOURS: Final[str] = "This review isn't yours."
NOT_IN_POOL: Final[str] = "You cannot review this captain."
TRAIT_UNUSED: Final[str] = "That trait is no longer used. Finish on the site."
_CLOSED_CODES: Final[frozenset[str]] = frozenset(
    {"snapshot_voided", "review_window_closed"}
)
_ATTACHABLE: Final[frozenset[DMStatus]] = frozenset(
    {DMStatus.PENDING, DMStatus.UNKNOWN}
)


def review_url(event_id: int, snapshot_id: int) -> str:
    return f"{settings.SITE_URL}/events/{event_id}?review={snapshot_id}"


def _discord_id(raw: str | None) -> str | None:
    return raw if raw and raw.isdigit() and len(raw) <= 20 else None


def _trait_parts(
    traits: Sequence[CaptainTrait], *, sample_ids: bool = False
) -> list[list[TraitRow]]:
    active = sorted((t for t in traits if t.active), key=lambda t: (t.order, t.pk))
    rows = [
        TraitRow(trait_id=index if sample_ids else t.pk, label=t.label, active=True)
        for index, t in enumerate(active, start=1)
    ]
    return [
        rows[i : i + MAX_TRAITS_PER_MESSAGE]
        for i in range(0, len(rows), MAX_TRAITS_PER_MESSAGE)
    ]


def preview(org_id: int, *, now: datetime) -> list[dict[str, Any]]:
    parts = _trait_parts(effective_traits(org_id), sample_ids=True)
    window = get_leadership_settings(org_id).review_window_hours
    return [
        render_part(
            captain_name="Sample Captain",
            event_name="Sample Event",
            close_at=now + timedelta(hours=window),
            part=index,
            parts=len(parts),
            traits=rows,
            scores={},
            snapshot_id=1,
            site_url="https://example.invalid/events/1?review=1",
            state="progress",
        )
        for index, rows in enumerate(parts, start=1)
    ]


def plan(
    event_id: int, snapshot_ids: Sequence[int], *, now: datetime
) -> list[PlannedMessage]:
    snaps = list(
        EventCaptain.objects.nocache()
        .filter(
            pk__in=list(snapshot_ids),
            event_id=event_id,
            voided_at__isnull=True,
            window_closes_at__gt=now,
        )
        .select_related("event", "captain__user")
        .prefetch_related(
            Prefetch(
                "teammates",
                queryset=OrgUser.objects.nocache().select_related("user"),
            )
        )
        .order_by("pk")
    )
    if not snaps:
        return []
    org_id = snaps[0].organization_id
    if not org_has_feature(org_id, FeatureKey.LEADERSHIP):
        return []
    dispatch = snaps[0].event.leadership_review_dm_dispatch or {}
    skip = None if get_leadership_settings(org_id).review_dms_enabled else "disabled"
    parts = _trait_parts(materialize_traits(org_id))
    messages: list[PlannedMessage] = []
    for snap in snaps:
        captain_name = user_display_name(snap.captain.user)
        mates = sorted(
            (
                m
                for m in snap.teammates.all()
                if m.pk != snap.captain_id and m.pk in dispatch.get(str(snap.pk), [])
            ),
            key=lambda m: m.pk,
        )
        for mate in mates:
            for index, rows in enumerate(parts, start=1):
                messages.append(
                    PlannedMessage(
                        snapshot_id=snap.pk,
                        part=index,
                        parts=len(parts),
                        trait_ids=[r.trait_id for r in rows],
                        rater_org_user_id=mate.pk,
                        recipient_user_id=mate.user_id,
                        organization_id=org_id,
                        discord_user_id=_discord_id(mate.user.discordId),
                        skip=skip,
                        payload=render_part(
                            captain_name=captain_name,
                            event_name=snap.event.name,
                            close_at=snap.window_closes_at,
                            part=index,
                            parts=len(parts),
                            traits=rows,
                            scores={},
                            snapshot_id=snap.pk,
                            site_url=review_url(snap.event_id, snap.pk),
                            state="progress",
                        ),
                    )
                )
    log.info(
        "leadership_review_dms_planned",
        system="org",
        subsystem="leadership",
        org_id=org_id,
        event_id=event_id,
        snapshots=len(snaps),
        messages=len(messages),
        disabled=skip is not None,
    )
    return messages


def _context_ints(context: Mapping[str, Any], key: str, default: int) -> int:
    value = context.get(key)
    return value if isinstance(value, int) else default


def _render(
    ec: EventCaptain,
    context: Mapping[str, Any],
    scores: Mapping[int, int],
    state: StatusState,
) -> dict[str, Any] | None:
    raw = context.get("trait_ids")
    ids = [i for i in raw if isinstance(i, int)] if isinstance(raw, list) else []
    by_pk = {
        t.pk: t
        for t in CaptainTrait.objects.nocache().filter(
            organization_id=ec.organization_id, pk__in=ids
        )
    }
    rows = [
        TraitRow(trait_id=i, label=by_pk[i].label, active=by_pk[i].active)
        for i in ids
        if i in by_pk
    ]
    if not rows:
        return None
    return render_part(
        captain_name=user_display_name(ec.captain.user),
        event_name=ec.event.name,
        close_at=ec.window_closes_at,
        part=_context_ints(context, "part", 1),
        parts=_context_ints(context, "parts", 1),
        traits=rows,
        scores=scores,
        snapshot_id=ec.pk,
        site_url=review_url(ec.event_id, ec.pk),
        state=state,
    )


def _int_scores(raw: Mapping[str, int]) -> dict[int, int]:
    return {int(k): v for k, v in raw.items()}


def _result(
    outcome: str,
    *,
    ledger_id: int | None = None,
    message: dict[str, Any] | None = None,
    ephemeral: str | None = None,
) -> ClickResult:
    log.info(
        "leadership_review_click",
        system="org",
        subsystem="leadership",
        ledger_id=ledger_id,
        outcome=outcome,
    )
    return ClickResult(message=message, ephemeral=ephemeral)


def _seed(draft: CaptainReviewDraft, live: CaptainReview | None) -> None:
    if live is None:
        return
    if (
        draft.seeded_from_review_at is not None
        and live.updated_at <= draft.seeded_from_review_at
    ):
        return
    draft.scores = {
        str(trait_id): value
        for trait_id, value in CaptainTraitScore.objects.nocache()
        .filter(review=live)
        .values_list("trait_id", "score")
    }
    draft.seeded_from_review_at = live.updated_at


def apply_click(
    *,
    discord_user_id: str,
    discord_message_id: str,
    discord_channel_id: str,
    snapshot_id: int,
    trait_id: int,
    score: int,
    now: datetime,
) -> ClickResult:
    with transaction.atomic():
        row = dm_ledger.find_leadership_row(
            snapshot_id=snapshot_id, discord_user_id=discord_user_id, trait_id=trait_id
        )
        if row is None:
            if dm_ledger.leadership_message_of_other(
                snapshot_id=snapshot_id,
                discord_message_id=discord_message_id,
                discord_user_id=discord_user_id,
            ):
                return _result("not_yours", ephemeral=NOT_YOURS)
            return _result("out_of_date", ephemeral=OUT_OF_DATE)
        if row.discord_message_id:
            if row.discord_message_id != discord_message_id:
                return _result("out_of_date", ledger_id=row.pk, ephemeral=OUT_OF_DATE)
        elif row.status not in _ATTACHABLE:
            return _result("out_of_date", ledger_id=row.pk, ephemeral=OUT_OF_DATE)
        else:
            try:
                dm_ledger.attach_on_click(
                    row.pk,
                    discord_user_id=discord_user_id,
                    discord_channel_id=discord_channel_id,
                    discord_message_id=discord_message_id,
                    now=now,
                )
            except (dm_ledger.LedgerConflict, dm_ledger.LedgerNotFound, IntegrityError):
                return _result("out_of_date", ledger_id=row.pk, ephemeral=OUT_OF_DATE)
        dm_ledger.record_click(
            discord_message_id=discord_message_id,
            discord_user_id=discord_user_id,
            now=now,
        )
        context: Mapping[str, Any] = (
            row.context if isinstance(row.context, dict) else {}
        )

        ec = (
            EventCaptain.objects.nocache()
            .select_for_update()
            .select_related("event", "captain__user", "organization")
            .filter(pk=snapshot_id)
            .first()
        )
        if ec is None:
            return _result("out_of_date", ledger_id=row.pk, ephemeral=OUT_OF_DATE)
        if not org_has_feature(ec.organization_id, FeatureKey.LEADERSHIP):
            return _result(
                "leadership_disabled",
                ledger_id=row.pk,
                ephemeral="Leadership is disabled for this organization.",
            )
        rater = (
            OrgUser.objects.nocache()
            .filter(organization_id=ec.organization_id, user__discordId=discord_user_id)
            .order_by("pk")
            .first()
        )
        if rater is None:
            return _result("not_in_pool", ledger_id=row.pk, ephemeral=NOT_IN_POOL)
        try:
            existing = check_rater_writable(ec, rater, now=max(now, timezone.now()))
        except ReviewRefused as exc:
            message = None
            if exc.code in _CLOSED_CODES:
                draft = CaptainReviewDraft.objects.filter(
                    event_captain=ec, rater=rater
                ).first()
                scores = _int_scores(draft.scores) if draft is not None else {}
                message = _render(ec, context, scores, "closed")
            return _result(
                exc.code, ledger_id=row.pk, message=message, ephemeral=exc.detail
            )

        trait = (
            CaptainTrait.objects.nocache()
            .filter(pk=trait_id, organization_id=ec.organization_id)
            .first()
        )
        if trait is None or not trait.active:
            return _result("trait_unused", ledger_id=row.pk, ephemeral=TRAIT_UNUSED)

        draft, _ = CaptainReviewDraft.objects.select_for_update().get_or_create(
            event_captain=ec, rater=rater
        )
        live = existing if existing is not None and existing.voided_at is None else None
        _seed(draft, live)
        draft.scores = {**draft.scores, str(trait_id): score}

        active = {t.pk: t for t in materialize_traits(ec.organization_id) if t.active}
        state: StatusState = "progress"
        if set(active) <= {int(k) for k in draft.scores}:
            try:
                review = submit_review(
                    ec.organization,
                    event_id=ec.event_id,
                    captain_org_user_id=ec.captain_id,
                    rater=rater,
                    scores={t.key: draft.scores[str(pk)] for pk, t in active.items()},
                    now=now,
                )
            except ReviewRefused as exc:
                draft.save()
                return _result(exc.code, ledger_id=row.pk, ephemeral=exc.detail)
            draft.seeded_from_review_at = review.updated_at
            state = "saved"
        elif not set(active) <= dm_ledger.leadership_trait_ids(
            snapshot_id=snapshot_id, discord_user_id=discord_user_id
        ):
            state = "traits_changed"
        draft.save()
        return _result(
            state,
            ledger_id=row.pk,
            message=_render(ec, context, _int_scores(draft.scores), state),
        )
