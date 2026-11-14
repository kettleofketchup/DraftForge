"""Request plumbing for the tournament list: params, search, cache key, page envelope."""

import binascii
from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Any, Literal, cast
from urllib.parse import urlencode

from django.db.models import Q
from django.http import QueryDict
from rest_framework.exceptions import ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.request import Request
from rest_framework.utils.urls import remove_query_param, replace_query_param

DEFAULT_PAGE_SIZE = 24
MAX_PAGE_SIZE = 100
SEARCH_MIN = 2
SEARCH_MAX = 64
MAX_ORGANIZATIONS = 100
ORGANIZATIONS_MINE = "mine"
TOURNAMENTS_LIST_CACHE_PREFIX = "tournaments_list_v6"

Bucket = Literal["upcoming", "archived"]
BUCKETS: tuple[Bucket, ...] = ("upcoming", "archived")

BUCKET_MESSAGE = "Must be 'upcoming' or 'archived'."
INTEGER_MESSAGE = "A valid integer is required."
MIN_ONE_MESSAGE = "Must be at least 1."
REQUIRES_BUCKET_MESSAGE = "Requires 'bucket'."
ORGANIZATIONS_MESSAGE = (
    f"Must be '{ORGANIZATIONS_MINE}' or a comma-separated list of positive integers."
)
TOO_MANY_ORGANIZATIONS_MESSAGE = f"At most {MAX_ORGANIZATIONS} organizations."
ORGANIZATION_CONFLICT_MESSAGE = "Use either 'organization' or 'organizations'."
OPEN_SIGNUPS_MESSAGE = "Must be '1' or '0'."
CURSOR_MESSAGE = "Invalid cursor."
CURSOR_BUCKET_MESSAGE = "Requires 'bucket=archived'."
CURSOR_PAGE_MESSAGE = "Use either 'page' or 'cursor'."


@dataclass(frozen=True)
class ArchiveCursor:
    """Keyset position in the archived order (date_played desc, pk desc)."""

    date_played: datetime
    pk: int

    @property
    def token(self) -> str:
        raw = f"{self.date_played.astimezone(UTC).isoformat()}|{self.pk}"
        return urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def archive_after_q(cursor: ArchiveCursor) -> Q:
    """Rows strictly after ``cursor`` in the archived order."""
    return Q(date_played__lt=cursor.date_played) | Q(
        date_played=cursor.date_played, pk__lt=cursor.pk
    )


def decode_archive_cursor(token: str) -> ArchiveCursor:
    try:
        raw = urlsafe_b64decode(token + "=" * (-len(token) % 4)).decode()
        played_text, pk_text = raw.split("|")
        played = datetime.fromisoformat(played_text)
        pk = int(pk_text)
    except (binascii.Error, UnicodeDecodeError, ValueError) as exc:
        raise ValueError(CURSOR_MESSAGE) from exc
    if not token or played.tzinfo is None or pk < 1:
        raise ValueError(CURSOR_MESSAGE)
    return ArchiveCursor(played.astimezone(UTC), pk)


@dataclass(frozen=True)
class TournamentListParams:
    organization: int | None
    organizations: tuple[int, ...] | None
    organizations_mine: bool
    open_signups: bool
    league: int | None
    bucket: Bucket | None
    search: str | None
    page: int | None
    page_size: int
    cursor: ArchiveCursor | None = None

    @property
    def paginated(self) -> bool:
        return self.page is not None or self.cursor is not None


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


def _parse_organizations(
    query_params: QueryDict, errors: dict[str, list[str]]
) -> tuple[int, ...] | None:
    raw = query_params.get("organizations")
    if raw is None:
        return None
    if raw.strip() in ("", ORGANIZATIONS_MINE):
        return ()
    ids: set[int] = set()
    for part in raw.split(","):
        text = part.strip()
        if not (text.isascii() and text.isdigit()) or int(text) < 1:
            errors["organizations"] = [ORGANIZATIONS_MESSAGE]
            return None
        ids.add(int(text))
    if len(ids) > MAX_ORGANIZATIONS:
        errors["organizations"] = [TOO_MANY_ORGANIZATIONS_MESSAGE]
        return None
    return tuple(sorted(ids))


def _parse_open_signups(query_params: QueryDict, errors: dict[str, list[str]]) -> bool:
    raw = query_params.get("open_signups")
    if raw is None or raw == "0":
        return False
    if raw == "1":
        return True
    errors["open_signups"] = [OPEN_SIGNUPS_MESSAGE]
    return False


def _parse_cursor(
    query_params: QueryDict, raw_bucket: str | None, errors: dict[str, list[str]]
) -> ArchiveCursor | None:
    raw = query_params.get("cursor")
    if raw is None:
        return None
    if raw_bucket != "archived":
        errors["cursor"] = [CURSOR_BUCKET_MESSAGE]
        return None
    if "page" in query_params:
        errors["cursor"] = [CURSOR_PAGE_MESSAGE]
        return None
    try:
        return decode_archive_cursor(raw)
    except ValueError:
        errors["cursor"] = [CURSOR_MESSAGE]
        return None


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
    organizations = _parse_organizations(query_params, errors)
    if "organization" in query_params and "organizations" in query_params:
        errors["organizations"] = [ORGANIZATION_CONFLICT_MESSAGE]
    organizations_mine = (query_params.get("organizations") or "").strip() == (
        ORGANIZATIONS_MINE
    )
    open_signups = _parse_open_signups(query_params, errors)
    league = _parse_int(query_params, "league", errors)
    page = _parse_int(query_params, "page", errors, min_value=1)
    page_size = _parse_int(query_params, "page_size", errors, min_value=1)

    if "page" in query_params and raw_bucket is None and "page" not in errors:
        errors["page"] = [REQUIRES_BUCKET_MESSAGE]
    cursor = _parse_cursor(query_params, raw_bucket, errors)

    if errors:
        raise ValidationError(errors)

    return TournamentListParams(
        organization=organization,
        organizations=organizations,
        organizations_mine=organizations_mine,
        open_signups=open_signups,
        league=league,
        bucket=bucket,
        search=normalize_search(query_params.get("search")),
        page=page,
        page_size=min(page_size or DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE),
        cursor=cursor,
    )


def resolve_organizations(
    params: TournamentListParams, member_ids: Callable[[], Iterable[int]]
) -> TournamentListParams:
    """Expand ``organizations=mine`` into the viewer's member organization ids."""
    if not params.organizations_mine:
        return params
    return replace(params, organizations=tuple(sorted(set(member_ids()))))


def tournaments_list_cache_key(params: TournamentListParams, cutoff: datetime) -> str:
    pairs: list[tuple[str, str]] = []
    for name in ("organization", "league", "bucket", "search", "page"):
        value = getattr(params, name)
        if value is not None:
            pairs.append((name, str(value)))
    if params.organizations is not None:
        pairs.append(("organizations", ",".join(map(str, params.organizations))))
    if params.open_signups:
        pairs.append(("open_signups", "1"))
    if params.cursor is not None:
        pairs.append(("cursor", params.cursor.token))
    if params.paginated:
        pairs.append(("page_size", str(params.page_size)))
    return (
        f"{TOURNAMENTS_LIST_CACHE_PREFIX}:{cutoff.date().isoformat()}"
        f":{urlencode(sorted(pairs))}"
    )


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


def build_cursor_envelope(
    request: Request,
    *,
    count: int,
    next_cursor: str | None,
    results: list[Any],
) -> dict[str, Any]:
    """Forward-only envelope: ``next`` carries the keyset cursor, ``previous`` is null."""
    next_url = None
    if next_cursor is not None:
        url = remove_query_param(request.build_absolute_uri(), "page")
        next_url = replace_query_param(url, "cursor", next_cursor)
    return {"count": count, "next": next_url, "previous": None, "results": results}
