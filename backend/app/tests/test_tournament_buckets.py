"""Pure helpers behind the bucketed tournament list: cutoff, params, cache key, envelope."""

from base64 import urlsafe_b64encode
from datetime import UTC, datetime, timedelta, timezone
from unittest import mock

from django.db.models import Case, Q
from django.http import QueryDict
from django.test import SimpleTestCase
from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from app.tournament_buckets import (
    tournament_bucket_cutoff,
    upcoming_q,
    upcoming_rank,
    utc_day_start,
)
from app.tournament_list import (
    DEFAULT_PAGE_SIZE,
    MAX_PAGE_SIZE,
    ArchiveCursor,
    TournamentListPagination,
    build_cursor_envelope,
    build_page_envelope,
    decode_archive_cursor,
    normalize_search,
    parse_tournament_list_params,
    resolve_organizations,
    tournaments_list_cache_key,
)

NOW = datetime(2026, 11, 13, 15, 30, tzinfo=UTC)
CUTOFF = datetime(2026, 11, 11, tzinfo=UTC)


class TournamentBucketCutoffTests(SimpleTestCase):
    def test_cutoff_is_midnight_two_days_back(self) -> None:
        self.assertEqual(tournament_bucket_cutoff(NOW), CUTOFF)

    def test_cutoff_at_exact_midnight(self) -> None:
        self.assertEqual(
            tournament_bucket_cutoff(datetime(2026, 11, 13, tzinfo=UTC)), CUTOFF
        )

    def test_cutoff_defaults_to_patched_clock(self) -> None:
        with mock.patch("app.tournament_buckets._now", return_value=NOW):
            self.assertEqual(tournament_bucket_cutoff(), CUTOFF)

    def test_utc_day_start_converts_non_utc_now(self) -> None:
        plus_five = datetime(2026, 11, 13, 1, tzinfo=timezone(timedelta(hours=5)))
        start = utc_day_start(plus_five)
        self.assertEqual(start, datetime(2026, 11, 12, tzinfo=UTC))
        self.assertEqual(start.utcoffset(), timedelta(0))

    def test_upcoming_q_filters_state_and_cutoff(self) -> None:
        self.assertEqual(
            upcoming_q(CUTOFF),
            Q(state__in=["future", "in_progress"], date_played__gte=CUTOFF),
        )

    def test_upcoming_rank_is_case(self) -> None:
        self.assertIsInstance(upcoming_rank(datetime(2026, 11, 13, tzinfo=UTC)), Case)


class NormalizeSearchTests(SimpleTestCase):
    def test_normalize_search(self) -> None:
        self.assertIsNone(normalize_search(None))
        self.assertIsNone(normalize_search("  "))
        self.assertIsNone(normalize_search(" a "))
        self.assertEqual(normalize_search(" ab "), "ab")
        self.assertEqual(normalize_search("x" * 70), "x" * 64)


class ParseTournamentListParamsTests(SimpleTestCase):
    def test_parse_rejects_bad_values(self) -> None:
        cases = [
            ("bucket=bogus", "bucket"),
            ("organization=abc", "organization"),
            ("league=x", "league"),
            ("bucket=archived&page=x", "page"),
            ("bucket=archived&page_size=x", "page_size"),
            ("bucket=archived&page=0", "page"),
            ("bucket=archived&page_size=0", "page_size"),
            ("bucket=archived&page_size=-5", "page_size"),
            ("page=1", "page"),
        ]
        for qs, field in cases:
            with self.subTest(qs=qs):
                with self.assertRaises(ValidationError) as ctx:
                    parse_tournament_list_params(QueryDict(qs))
                self.assertIn(field, ctx.exception.detail)

    def test_parse_messages(self) -> None:
        cases = [
            ("bucket=bogus", {"bucket": ["Must be 'upcoming' or 'archived'."]}),
            ("organization=abc", {"organization": ["A valid integer is required."]}),
            ("bucket=archived&page=0", {"page": ["Must be at least 1."]}),
            ("page=1", {"page": ["Requires 'bucket'."]}),
        ]
        for qs, expected in cases:
            with self.subTest(qs=qs):
                with self.assertRaises(ValidationError) as ctx:
                    parse_tournament_list_params(QueryDict(qs))
                self.assertEqual(ctx.exception.detail, expected)

    def test_parse_valid(self) -> None:
        params = parse_tournament_list_params(
            QueryDict("organization=007&league= 3 &bucket=upcoming&search= ab ")
        )
        self.assertEqual(params.organization, 7)
        self.assertEqual(params.league, 3)
        self.assertEqual(params.bucket, "upcoming")
        self.assertEqual(params.search, "ab")
        self.assertIsNone(params.page)
        self.assertEqual(params.page_size, DEFAULT_PAGE_SIZE)

    def test_parse_empty(self) -> None:
        params = parse_tournament_list_params(QueryDict(""))
        self.assertIsNone(params.organization)
        self.assertIsNone(params.league)
        self.assertIsNone(params.bucket)
        self.assertIsNone(params.search)
        self.assertIsNone(params.page)

    def test_parse_caps_page_size(self) -> None:
        capped = parse_tournament_list_params(
            QueryDict("bucket=archived&page=1&page_size=500")
        )
        self.assertEqual(capped.page_size, MAX_PAGE_SIZE)
        self.assertEqual(capped.page, 1)
        default = parse_tournament_list_params(QueryDict("bucket=archived&page=1"))
        self.assertEqual(default.page_size, DEFAULT_PAGE_SIZE)

    def test_parse_organization_zero_is_valid(self) -> None:
        params = parse_tournament_list_params(QueryDict("organization=0"))
        self.assertEqual(params.organization, 0)


class ResolveOrganizationsTests(SimpleTestCase):
    def test_mine_expands_sorted_and_deduped(self) -> None:
        params = parse_tournament_list_params(QueryDict("organizations=mine"))
        self.assertTrue(params.organizations_mine)
        resolved = resolve_organizations(params, lambda: [5, 2, 5])
        self.assertEqual(resolved.organizations, (2, 5))

    def test_explicit_ids_skip_the_lookup(self) -> None:
        params = parse_tournament_list_params(QueryDict("organizations=3"))
        lookup = mock.Mock(return_value=[9])
        self.assertEqual(resolve_organizations(params, lookup).organizations, (3,))
        lookup.assert_not_called()

    def test_mine_cache_key_matches_the_expanded_ids(self) -> None:
        mine = resolve_organizations(
            parse_tournament_list_params(QueryDict("organizations=mine")),
            lambda: [2, 1],
        )
        explicit = parse_tournament_list_params(QueryDict("organizations=1,2"))
        self.assertEqual(
            tournaments_list_cache_key(mine, CUTOFF),
            tournaments_list_cache_key(explicit, CUTOFF),
        )


class TournamentsListCacheKeyTests(SimpleTestCase):
    def _key(self, qs: str, cutoff: datetime = CUTOFF) -> str:
        return tournaments_list_cache_key(
            parse_tournament_list_params(QueryDict(qs)), cutoff
        )

    def test_cache_key_drops_unknown_and_normalizes_ints(self) -> None:
        a = self._key("organization=007&utm=x")
        b = self._key("organization=7")
        self.assertEqual(a, b)
        self.assertIn("2026-11-11", a)
        self.assertTrue(a.startswith("tournaments_list_v6:"))

    def test_cache_key_is_order_independent(self) -> None:
        self.assertEqual(
            self._key("league=2&bucket=upcoming"), self._key("bucket=upcoming&league=2")
        )

    def test_cache_key_normalizes_search(self) -> None:
        self.assertEqual(self._key("search=%20ab%20"), self._key("search=ab"))
        self.assertEqual(self._key("search=a"), self._key(""))

    def test_cache_key_records_effective_page_size(self) -> None:
        self.assertEqual(
            self._key("bucket=archived&page=1&page_size=500"),
            self._key("bucket=archived&page=1&page_size=100"),
        )
        self.assertEqual(
            self._key("bucket=archived&page=1"),
            self._key("bucket=archived&page=1&page_size=24"),
        )

    def test_cache_key_ignores_page_size_without_page(self) -> None:
        self.assertEqual(
            self._key("bucket=archived&page_size=5"), self._key("bucket=archived")
        )

    def test_cache_key_differs_by_page(self) -> None:
        self.assertNotEqual(
            self._key("bucket=archived&page=1"), self._key("bucket=archived&page=2")
        )

    def test_cache_key_differs_by_cutoff(self) -> None:
        self.assertNotEqual(
            self._key("bucket=upcoming"),
            self._key("bucket=upcoming", datetime(2026, 11, 12, tzinfo=UTC)),
        )

    def test_cache_key_normalizes_organizations(self) -> None:
        self.assertEqual(
            self._key("organizations=3,1,3&open_signups=1"),
            self._key("open_signups=1&organizations=1, 3"),
        )
        self.assertNotEqual(self._key("organizations="), self._key(""))
        self.assertNotEqual(
            self._key("organizations=1&open_signups=1"), self._key("organizations=1")
        )
        self.assertEqual(
            self._key("organizations=1&open_signups=0"), self._key("organizations=1")
        )

    def test_cache_key_reads_prefix_at_call_time(self) -> None:
        with mock.patch("app.tournament_list.TOURNAMENTS_LIST_CACHE_PREFIX", "other"):
            self.assertTrue(self._key("bucket=upcoming").startswith("other:"))


class BuildPageEnvelopeTests(SimpleTestCase):
    def _req(self, qs: str) -> Request:
        return Request(APIRequestFactory().get(f"/api/tournaments-list/?{qs}"))

    def test_envelope_first_middle_last(self) -> None:
        env = build_page_envelope(
            self._req("bucket=archived&page=1"),
            count=50,
            page=1,
            page_size=24,
            results=[],
        )
        self.assertIsNone(env["previous"])
        self.assertIn("page=2", env["next"])
        self.assertEqual(env["count"], 50)
        self.assertEqual(env["results"], [])

        env2 = build_page_envelope(
            self._req("bucket=archived&page=2"),
            count=50,
            page=2,
            page_size=24,
            results=[],
        )
        self.assertNotIn("page=", env2["previous"])
        self.assertIn("bucket=archived", env2["previous"])
        self.assertIn("page=3", env2["next"])

        env3 = build_page_envelope(
            self._req("bucket=archived&page=3"),
            count=50,
            page=3,
            page_size=24,
            results=[],
        )
        self.assertIsNone(env3["next"])
        self.assertIn("page=2", env3["previous"])

    def test_envelope_exact_fit_has_no_next(self) -> None:
        env = build_page_envelope(
            self._req("bucket=archived&page=2"),
            count=48,
            page=2,
            page_size=24,
            results=[],
        )
        self.assertIsNone(env["next"])

    def test_envelope_keys(self) -> None:
        env = build_page_envelope(
            self._req("bucket=archived&page=1"),
            count=1,
            page=1,
            page_size=24,
            results=[{"pk": 1}],
        )
        self.assertEqual(set(env), {"count", "next", "previous", "results"})
        self.assertEqual(env["results"], [{"pk": 1}])


class ArchiveCursorTests(SimpleTestCase):
    def test_round_trip(self) -> None:
        cursor = ArchiveCursor(datetime(2026, 11, 1, 18, 30, 5, 123456, tzinfo=UTC), 42)
        self.assertEqual(decode_archive_cursor(cursor.token), cursor)

    def test_token_is_url_safe_and_unpadded(self) -> None:
        token = ArchiveCursor(datetime(2026, 11, 1, tzinfo=UTC), 7).token
        self.assertRegex(token, r"^[A-Za-z0-9_-]+$")

    def test_non_utc_input_normalizes_to_utc(self) -> None:
        plus_two = datetime(2026, 11, 1, 2, tzinfo=timezone(timedelta(hours=2)))
        utc = datetime(2026, 11, 1, tzinfo=UTC)
        self.assertEqual(ArchiveCursor(plus_two, 7).token, ArchiveCursor(utc, 7).token)

    def test_rejects_malformed_tokens(self) -> None:
        naive = ArchiveCursor(datetime(2026, 11, 1, tzinfo=UTC), 7).token
        bad = [
            "",
            "%%",
            "bm9wZQ",
            naive[:-3],
            _b64("2026-11-01T00:00:00|7"),
            _b64("2026-11-01T00:00:00+00:00|0"),
            _b64("2026-11-01T00:00:00+00:00|x"),
            _b64("not-a-date|7"),
            _b64("2026-11-01T00:00:00+00:00"),
        ]
        for token in bad:
            with self.subTest(token=token):
                with self.assertRaises(ValueError):
                    decode_archive_cursor(token)

    def test_parse_reads_cursor(self) -> None:
        cursor = ArchiveCursor(datetime(2026, 11, 1, tzinfo=UTC), 7)
        params = parse_tournament_list_params(
            QueryDict(f"bucket=archived&cursor={cursor.token}&page_size=5")
        )
        self.assertEqual(params.cursor, cursor)
        self.assertIsNone(params.page)
        self.assertTrue(params.paginated)
        self.assertFalse(
            parse_tournament_list_params(QueryDict("bucket=archived")).paginated
        )

    def test_parse_cursor_errors(self) -> None:
        token = ArchiveCursor(datetime(2026, 11, 1, tzinfo=UTC), 7).token
        cases = [
            ("bucket=archived&cursor=%%", {"cursor": ["Invalid cursor."]}),
            (
                f"bucket=upcoming&cursor={token}",
                {"cursor": ["Requires 'bucket=archived'."]},
            ),
            (f"cursor={token}", {"cursor": ["Requires 'bucket=archived'."]}),
            (
                f"bucket=archived&page=1&cursor={token}",
                {"cursor": ["Use either 'page' or 'cursor'."]},
            ),
        ]
        for qs, expected in cases:
            with self.subTest(qs=qs):
                with self.assertRaises(ValidationError) as ctx:
                    parse_tournament_list_params(QueryDict(qs))
                self.assertEqual(ctx.exception.detail, expected)

    def test_cache_key_includes_cursor_and_page_size(self) -> None:
        a = ArchiveCursor(datetime(2026, 11, 1, tzinfo=UTC), 7).token
        b = ArchiveCursor(datetime(2026, 11, 1, tzinfo=UTC), 6).token

        def key(qs: str) -> str:
            return tournaments_list_cache_key(
                parse_tournament_list_params(QueryDict(qs)), CUTOFF
            )

        self.assertNotEqual(
            key(f"bucket=archived&cursor={a}"), key(f"bucket=archived&cursor={b}")
        )
        self.assertNotEqual(
            key(f"bucket=archived&cursor={a}"), key("bucket=archived&page=1")
        )
        self.assertNotEqual(key(f"bucket=archived&cursor={a}"), key("bucket=archived"))
        self.assertNotEqual(
            key(f"bucket=archived&cursor={a}&page_size=5"),
            key(f"bucket=archived&cursor={a}&page_size=10"),
        )
        self.assertEqual(
            key(f"bucket=archived&cursor={a}"),
            key(f"bucket=archived&cursor={a}&page_size=24"),
        )

    def test_cursor_envelope(self) -> None:
        req = Request(
            APIRequestFactory().get(
                "/api/tournaments-list/?bucket=archived&page=1&page_size=2"
            )
        )
        env = build_cursor_envelope(
            req, count=5, next_cursor="abc", results=[{"pk": 1}]
        )
        self.assertEqual(set(env), {"count", "next", "previous", "results"})
        self.assertIsNone(env["previous"])
        self.assertIn("cursor=abc", env["next"])
        self.assertIn("page_size=2", env["next"])
        self.assertNotIn("page=", env["next"].replace("page_size=", ""))
        last = build_cursor_envelope(req, count=5, next_cursor=None, results=[])
        self.assertIsNone(last["next"])


def _b64(text: str) -> str:
    return urlsafe_b64encode(text.encode()).decode().rstrip("=")


class TournamentListPaginationTests(SimpleTestCase):
    def test_pagination_settings(self) -> None:
        self.assertEqual(TournamentListPagination.page_size, 24)
        self.assertEqual(TournamentListPagination.page_size_query_param, "page_size")
        self.assertEqual(TournamentListPagination.max_page_size, 100)
