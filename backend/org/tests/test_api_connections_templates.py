import json
from typing import Any

from django.test import SimpleTestCase

from app.models import CustomUser
from common.game import GameType
from org.api_connections.mapping import MappingError, map_page
from org.api_connections.pagination import PaginationError, next_position
from org.api_connections.schemas import validate_connection_config
from org.api_connections.templates import TemplateError, render_request
from org.api_connections.types import (
    ConnectionConfig,
    MappedPage,
    MemberSnapshot,
    SnapshotMember,
)

BASE = CustomUser.STEAM_ID_64_BASE


def config(**pull: Any) -> ConnectionConfig:
    raw: dict[str, Any] = {
        "outbound_base_url": "https://sync.example.test/base",
        "outbound_auth": pull.pop("auth", "none"),
        "game_type": int(GameType.DOTA2),
        "mmr_pull_config": {"path": "/players/{org_id}", **pull},
    }
    return validate_connection_config(raw)


def snapshot(*members: SnapshotMember) -> MemberSnapshot:
    return MemberSnapshot(organization_id=7, game_type=GameType.DOTA2, members=members)


ALICE = SnapshotMember(
    org_user_id=1, steam_account_id=4_000_000_000, discord_id="900000000000000001"
)
BOB = SnapshotMember(org_user_id=2, steam_account_id=None, discord_id=None)


class RenderRequestTests(SimpleTestCase):
    def test_structural_arrays_preserve_large_decimal_ids(self) -> None:
        cfg = config(
            method="POST",
            query={"ids": "{{players.steam64_ids}}", "org": "{{org.id}}"},
            body={
                "players": "{{players.steam64_ids}}",
                "discord": "{{players.discord_ids}}",
                "nested": {"game": "{{game_type}}"},
            },
        )
        request = render_request(
            cfg, snapshot(ALICE, BOB), page=None, cursor=None, credential=None
        )
        steam64 = str(4_000_000_000 + BASE)
        self.assertEqual(request.url, "https://sync.example.test/base/players/7")
        self.assertEqual(request.method, "POST")
        self.assertEqual(request.query, {"ids": steam64, "org": 7})
        self.assertEqual(
            request.body,
            {
                "players": [steam64],
                "discord": ["900000000000000001"],
                "nested": {"game": GameType.DOTA2},
            },
        )
        self.assertNotIn("None", json.dumps(request.body) + json.dumps(request.query))

    def test_missing_identifier_never_sends_none(self) -> None:
        cfg = config(request_mode="per_member", query={"id": "{{player.steam64}}"})
        with self.assertRaises(TemplateError) as raised:
            render_request(cfg, snapshot(BOB), page=None, cursor=None, credential=None)
        self.assertEqual(raised.exception.code, "missing_identifier")
        batch = render_request(
            config(query={"ids": "{{players.discord_ids}}"}),
            snapshot(BOB),
            page=None,
            cursor=None,
            credential=None,
        )
        self.assertEqual(batch.query, {"ids": ""})
        rendered = render_request(
            cfg, snapshot(ALICE), page=None, cursor=None, credential=None
        )
        self.assertEqual(rendered.query, {"id": str(4_000_000_000 + BASE)})

    def test_pagination_placeholders_and_cursor_omission(self) -> None:
        cfg = config(
            query={"p": "{{page}}", "n": "{{page_size}}", "c": "{{cursor}}"},
            pagination={"kind": "page", "start": 1, "page_size": 50},
        )
        first = render_request(cfg, snapshot(), page=1, cursor=None, credential=None)
        self.assertEqual(first.query, {"p": 1, "n": 50})
        later = render_request(cfg, snapshot(), page=2, cursor="ab", credential=None)
        self.assertEqual(later.query, {"p": 2, "n": 50, "c": "ab"})

    def test_credential_slot_is_filled_only_by_transport(self) -> None:
        cfg = validate_connection_config(
            {
                "outbound_base_url": "https://sync.example.test",
                "outbound_auth": "api_key_field",
                "mmr_pull_config": {
                    "query": {"api_key": "{{credential}}", "x": "1"},
                    "credential_field": {"location": "query", "key": "api_key"},
                },
            }
        )
        request = render_request(
            cfg, snapshot(), page=None, cursor=None, credential="sekret-value"
        )
        self.assertEqual(request.query, {"x": "1"})
        self.assertEqual(request.credential, "sekret-value")
        self.assertEqual(request.credential_origin, "https://sync.example.test:443")
        self.assertEqual(request.credential_field.key, "api_key")
        self.assertNotIn("sekret-value", repr(request))
        with self.assertRaises(TemplateError):
            render_request(cfg, snapshot(), page=None, cursor=None, credential=None)


class MapPageTests(SimpleTestCase):
    def test_root_and_nested_list_paths(self) -> None:
        cfg = config(mapping={"list_path": "", "player_id_path": "id"})
        page = map_page([{"id": 5, "mmr": 3000}], cfg, page=1)
        self.assertEqual(page.rows[0].player_id, "5")
        self.assertEqual(page.rows[0].mmr, 3000)
        nested = config(
            mapping={
                "list_path": "data.items",
                "player_id_path": "player.ids.0",
                "player_id_type": "steam64",
                "mmr_path": "rank.mmr",
            }
        )
        big = 76561198000000123
        payload = {"data": {"items": [{"player": {"ids": [big]}, "rank": {"mmr": 1}}]}}
        mapped = map_page(payload, nested, page=3)
        self.assertEqual(mapped.rows[0].player_id, str(big))
        self.assertEqual((mapped.rows[0].page, mapped.rows[0].index), (3, 0))

    def test_malformed_envelope_fails(self) -> None:
        cfg = config(mapping={"list_path": "data"})
        for payload in ({"data": {}}, {"other": []}, [], None, "x"):
            with self.subTest(payload=payload), self.assertRaises(MappingError):
                map_page(payload, cfg, page=1)

    def test_strict_mmr_and_identifier_values(self) -> None:
        cfg = config()
        rows = [
            {"id": 1, "mmr": None},
            {"id": 2, "mmr": True},
            {"id": 3, "mmr": "3000"},
            {"id": 4, "mmr": 3000.0},
            {"id": 5},
            {"mmr": 10},
            {"id": 7.0, "mmr": 10},
            {"id": True, "mmr": 10},
            {"id": "0012", "mmr": 10},
            {"id": 9, "mmr": 99_999_999},
            "nope",
        ]
        mapped = map_page(rows, cfg, page=1)
        self.assertEqual(
            [(r.player_id, r.mmr, r.error) for r in mapped.rows],
            [
                ("1", None, None),
                ("2", None, "invalid_mmr"),
                ("3", None, "invalid_mmr"),
                ("4", None, "invalid_mmr"),
                ("5", None, "missing_mmr"),
                (None, None, "missing_identifier"),
                (None, None, "invalid_identifier"),
                (None, None, "invalid_identifier"),
                ("12", 10, None),
                ("9", None, "invalid_mmr"),
                (None, None, "invalid_entry"),
            ],
        )

    def test_has_more_and_cursor_types(self) -> None:
        cfg = config(
            mapping={"list_path": "items"},
            pagination={"kind": "cursor", "next_cursor_path": "next"},
        )
        self.assertEqual(map_page({"items": [], "next": 5}, cfg, page=1).next_cursor, 5)
        self.assertIsNone(map_page({"items": [], "next": ""}, cfg, page=1).next_cursor)
        for bad in (True, 1.5, {"a": 1}):
            with self.subTest(bad=bad), self.assertRaises(MappingError):
                map_page({"items": [], "next": bad}, cfg, page=1)
        with self.assertRaises(MappingError) as raised:
            map_page({"items": [], "next": "x" * 1025}, cfg, page=1)
        self.assertEqual(raised.exception.code, "cursor_too_large")
        more = config(
            mapping={"list_path": "items"},
            pagination={"kind": "page", "has_more_path": "meta.more"},
        )
        self.assertTrue(
            map_page({"items": [], "meta": {"more": True}}, more, page=1).has_more
        )
        with self.assertRaises(MappingError):
            map_page({"items": [], "meta": {"more": "yes"}}, more, page=1)


def mapped(count: int, *, has_more: bool = False, cursor: object = None) -> MappedPage:
    cfg = config()
    page = map_page([{"id": i + 1, "mmr": 10} for i in range(count)], cfg, page=1)
    return MappedPage(rows=page.rows, has_more=has_more, next_cursor=cursor)


class PaginationTests(SimpleTestCase):
    def test_page_mode_stops_on_short_or_empty_page(self) -> None:
        cfg = config(pagination={"kind": "page", "start": 0, "page_size": 2})
        self.assertEqual(next_position(cfg, mapped(2), page=0, seen=[]).page, 1)
        self.assertIsNone(next_position(cfg, mapped(1), page=0, seen=[]))
        self.assertIsNone(next_position(cfg, mapped(0), page=0, seen=[]))

    def test_has_more_path_controls_page_mode(self) -> None:
        cfg = config(
            pagination={"kind": "page", "page_size": 2, "has_more_path": "more"}
        )
        self.assertIsNone(next_position(cfg, mapped(2), page=1, seen=[]))
        self.assertEqual(
            next_position(cfg, mapped(1, has_more=True), page=1, seen=[]).page, 2
        )

    def test_cursor_loop_and_opaque_cursor_limit(self) -> None:
        cfg = config(pagination={"kind": "cursor", "next_cursor_path": "next"})
        step = next_position(cfg, mapped(1, cursor="a"), page=1, seen=[])
        self.assertEqual(step.cursor, "a")
        with self.assertRaises(PaginationError) as raised:
            next_position(cfg, mapped(1, cursor="a"), page=2, seen=["a"])
        self.assertEqual(raised.exception.code, "pagination_loop")
        self.assertIsNone(next_position(cfg, mapped(1), page=2, seen=["a"]))
        repeated = config(pagination={"kind": "page", "page_size": 1})
        first = next_position(repeated, mapped(1), page=1, seen=[])
        with self.assertRaises(PaginationError) as loop:
            next_position(repeated, mapped(1), page=2, seen=first.seen)
        self.assertEqual(loop.exception.code, "pagination_loop")

    def test_none_mode_never_continues(self) -> None:
        self.assertIsNone(next_position(config(), mapped(500), page=1, seen=[]))
