"""Count rows outside the team that point at a set of teams."""

from collections.abc import Iterable
from functools import reduce
from operator import or_
from typing import TypedDict

from django.db import models
from django.db.models import Q, QuerySet

from app.models import Team
from draft.models import DraftTeam, HeroDraft

_COUNTED_ON_DELETE = (models.CASCADE, models.SET_NULL)
# Audit rows outlive the team (SET_NULL); chat dies with it. Neither blocks a reset or delete.
_EXCLUDED_KEYS = frozenset(
    {
        "app.TeamLog.team",
        "draft.HeroDraftChatMessage.team",
        "draft.HeroDraftChatMembership.team",
    }
)


def _reference_relations() -> list[models.ForeignObjectRel]:
    # include_hidden: related_name="+" FKs (lobby) are absent from related_objects.
    return [
        rel
        for rel in Team._meta.get_fields(include_hidden=True)
        if isinstance(rel, models.ForeignObjectRel)
        and (rel.one_to_many or rel.one_to_one)
        and not rel.related_model._meta.auto_created
        and rel.on_delete in _COUNTED_ON_DELETE
        and _key(rel) not in _EXCLUDED_KEYS
    ]


def _key(rel: models.ForeignObjectRel) -> str:
    return f"{rel.related_model._meta.label}.{rel.field.name}"


def all_reference_keys() -> list[str]:
    return [_key(rel) for rel in _reference_relations()]


class TeamRef(TypedDict):
    pk: int
    name: str


class TeamUsage(TypedDict):
    model: str
    label: str
    label_plural: str
    count: int
    teams: list[TeamRef]


# A HeroDraft has one DraftTeam per side; count the draft, not its sides.
_ROLLUPS: dict[type[models.Model], tuple[str, type[models.Model]]] = {
    DraftTeam: ("draft", HeroDraft),
}

_LABELS: dict[str, tuple[str, str]] = {
    "app.Game": ("game", "games"),
    "app.Tournament": ("tournament result", "tournament results"),
    "bracket.BracketSlot": ("bracket slot", "bracket slots"),
    "draft.HeroDraft": ("HeroDraft", "HeroDrafts"),
    "lobby.GameLobby": ("lobby", "lobbies"),
}


def _team_rows(teams: QuerySet[Team] | Iterable[Team]) -> dict[int, str]:
    if isinstance(teams, QuerySet):
        return dict(teams.order_by("pk").values_list("pk", "name"))
    return {team.pk: team.name for team in sorted(teams, key=lambda t: t.pk)}


def team_usage(teams: QuerySet[Team] | Iterable[Team]) -> list[TeamUsage]:
    """Distinct records per model that use ``teams``, with the teams each one touches."""
    names = _team_rows(teams)
    if not names:
        return []
    by_model: dict[type[models.Model], list[models.ForeignObjectRel]] = {}
    for rel in _reference_relations():
        by_model.setdefault(rel.related_model, []).append(rel)

    usage: list[TeamUsage] = []
    for model, rels in by_model.items():
        rows = model._base_manager.filter(
            reduce(or_, (Q(**{f"{rel.field.name}__in": list(names)}) for rel in rels))
        )
        counted = model
        rollup = _ROLLUPS.get(model)
        if rollup:
            field_name, counted = rollup
            count = rows.values(field_name).distinct().count()
        else:
            count = rows.count()
        if not count:
            continue
        label = counted._meta.label
        used: set[int] = set()
        for rel in rels:
            used.update(rows.values_list(rel.field.attname, flat=True))
        singular, plural = _LABELS.get(
            label,
            (
                str(counted._meta.verbose_name),
                str(counted._meta.verbose_name_plural),
            ),
        )
        usage.append(
            {
                "model": label,
                "label": singular,
                "label_plural": plural,
                "count": count,
                "teams": [
                    {"pk": pk, "name": name} for pk, name in names.items() if pk in used
                ],
            }
        )
    return sorted(usage, key=lambda u: u["model"])


def team_references(teams: QuerySet[Team] | Iterable[Team]) -> dict[str, int]:
    team_pks = (
        list(teams.values_list("pk", flat=True))
        if isinstance(teams, QuerySet)
        else [team.pk for team in teams]
    )
    if not team_pks:
        return {}
    counts: dict[str, int] = {}
    for rel in _reference_relations():
        count = rel.related_model._base_manager.filter(
            **{f"{rel.field.name}__in": team_pks}
        ).count()
        if count:
            counts[_key(rel)] = count
    return counts
