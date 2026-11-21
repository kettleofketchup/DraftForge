"""Check that a @cached_as block declares every model its body reads.

``record_cached_as(module)`` swaps ``module.cached_as`` for a recorder that
runs the decorated function uncached, captures its SQL, and keeps the
declared dependencies next to the models those queries touched.
``uncovered_reads()`` then lists the models read but not declared.
"""

import re
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any
from unittest import mock

from django.apps import apps
from django.db import connection
from django.db.models import Model, QuerySet
from django.test.utils import CaptureQueriesContext

_TABLE_RE = re.compile(r'\b(?:FROM|JOIN)\s+"([^"]+)"')


def _models_by_table() -> dict[str, type[Model]]:
    return {m._meta.db_table: m for m in apps.get_models(include_auto_created=True)}


def _dep_model(dep: Any) -> type[Model]:
    if isinstance(dep, QuerySet):
        return dep.model
    if isinstance(dep, Model):
        return type(dep)
    return dep


@dataclass
class CachedAsCall:
    deps: set[type[Model]]
    reads: set[type[Model]] = field(default_factory=set)

    def uncovered_reads(self) -> set[type[Model]]:
        missing = set()
        for model in self.reads:
            # An auto-created m2m through table is covered by its owner.
            owner = model._meta.auto_created or model
            if owner not in self.deps:
                missing.add(model)
        return missing


@contextmanager
def record_cached_as(module: ModuleType) -> Iterator[list[CachedAsCall]]:
    calls: list[CachedAsCall] = []
    tables = _models_by_table()

    def fake_cached_as(*deps: Any, **_kwargs: Any) -> Callable:
        def decorate(func: Callable) -> Callable:
            def run(*args: Any, **kwargs: Any) -> Any:
                call = CachedAsCall(deps={_dep_model(d) for d in deps})
                with CaptureQueriesContext(connection) as ctx:
                    result = func(*args, **kwargs)
                for query in ctx.captured_queries:
                    for table in _TABLE_RE.findall(query["sql"]):
                        if table in tables:
                            call.reads.add(tables[table])
                calls.append(call)
                return result

            return run

        return decorate

    with mock.patch.object(module, "cached_as", fake_cached_as):
        yield calls
