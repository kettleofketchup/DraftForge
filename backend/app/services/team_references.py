"""Count rows outside the team that point at a set of teams."""

from collections.abc import Iterable

from django.db import models
from django.db.models import QuerySet

from app.models import Team

_COUNTED_ON_DELETE = (models.CASCADE, models.SET_NULL)
# Audit rows outlive the team (SET_NULL); they never block a reset or delete.
_EXCLUDED_KEYS = frozenset({"app.TeamLog.team"})


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
