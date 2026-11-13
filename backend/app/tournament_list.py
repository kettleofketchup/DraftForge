"""Request plumbing for the tournament list: params, search, cache key, page envelope."""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, cast
from urllib.parse import urlencode

from django.http import QueryDict
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.utils.urls import remove_query_param, replace_query_param

DEFAULT_PAGE_SIZE = 24
MAX_PAGE_SIZE = 100
SEARCH_MIN = 2
SEARCH_MAX = 64
TOURNAMENTS_LIST_CACHE_PREFIX = "tournaments_list_v3"

Bucket = Literal["upcoming", "archived"]
BUCKETS: tuple[Bucket, ...] = ("upcoming", "archived")

BUCKET_MESSAGE = "Must be 'upcoming' or 'archived'."
INTEGER_MESSAGE = "A valid integer is required."
MIN_ONE_MESSAGE = "Must be at least 1."
REQUIRES_BUCKET_MESSAGE = "Requires 'bucket'."


@dataclass(frozen=True)
class TournamentListParams:
    organization: int | None
    league: int | None
    bucket: Bucket | None
    search: str | None
    page: int | None
    page_size: int


class TournamentListPagination(PageNumberPagination):
    page_size = DEFAULT_PAGE_SIZE
    page_size_query_param = "page_size"
    max_page_size = MAX_PAGE_SIZE


def normalize_search(raw: str | None) -> str | None:
    if raw is None:
        return None
    text = raw.strip()
    if len(text) < SEARCH_MIN:
        return None
    return text[:SEARCH_MAX]


def _parse_int(
    query_params: QueryDict,
    field: str,
    errors: dict[str, list[str]],
    *,
    min_value: int | None = None,
) -> int | None:
    raw = query_params.get(field)
    if raw is None:
        return None
    try:
        value = int(raw.strip())
    except ValueError:
        errors[field] = [INTEGER_MESSAGE]
        return None
    if min_value is not None and value < min_value:
        errors[field] = [MIN_ONE_MESSAGE]
        return None
    return value


def parse_tournament_list_params(query_params: QueryDict) -> TournamentListParams:
    errors: dict[str, list[str]] = {}

    raw_bucket = query_params.get("bucket")
    bucket: Bucket | None = None
    if raw_bucket is not None:
        if raw_bucket in BUCKETS:
            bucket = cast(Bucket, raw_bucket)
        else:
            errors["bucket"] = [BUCKET_MESSAGE]

    organization = _parse_int(query_params, "organization", errors)
    league = _parse_int(query_params, "league", errors)
    page = _parse_int(query_params, "page", errors, min_value=1)
    page_size = _parse_int(query_params, "page_size", errors, min_value=1)

    if "page" in query_params and raw_bucket is None and "page" not in errors:
        errors["page"] = [REQUIRES_BUCKET_MESSAGE]

    if errors:
        raise ValidationError(errors)

    return TournamentListParams(
        organization=organization,
        league=league,
        bucket=bucket,
        search=normalize_search(query_params.get("search")),
        page=page,
        page_size=min(page_size or DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE),
    )


def tournaments_list_cache_key(params: TournamentListParams, cutoff: datetime) -> str:
    pairs: list[tuple[str, str]] = []
    for name in ("organization", "league", "bucket", "search", "page"):
        value = getattr(params, name)
        if value is not None:
            pairs.append((name, str(value)))
    if params.page is not None:
        pairs.append(("page_size", str(params.page_size)))
    return f"{TOURNAMENTS_LIST_CACHE_PREFIX}:{cutoff.date().isoformat()}:{urlencode(sorted(pairs))}"


def build_page_envelope(
    request: Request,
    *,
    count: int,
    page: int,
    page_size: int,
    results: list[Any],
) -> dict[str, Any]:
    url = request.build_absolute_uri()
    next_url = (
        replace_query_param(url, "page", page + 1) if page * page_size < count else None
    )
    if page == 1:
        previous_url = None
    elif page == 2:
        previous_url = remove_query_param(url, "page")
    else:
        previous_url = replace_query_param(url, "page", page - 1)
    return {
        "count": count,
        "next": next_url,
        "previous": previous_url,
        "results": results,
    }
