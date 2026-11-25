from datetime import timedelta
from typing import Any
from unittest.mock import patch

from app.models import CustomUser
from common.game import GameType
from org.mmr import set_org_mmr
from org.models import OrgUser, OrgUserGameMmr
from org.promotion.recipients import CandidateSource, candidates
from org.tests.test_promotion_sources import FETCH, _SourcesBase, guild_member

CAP = "org.promotion.recipients.MAX_DISCORD_ROWS"


class _MmrBase(_SourcesBase):
    def _mmr(
        self,
        user: CustomUser,
        mmr: int,
        *,
        org: Any = None,
        game: int = GameType.DOTA2,
    ) -> None:
        org_user, _ = OrgUser.objects.get_or_create(
            user=user, organization=org or self.org
        )
        OrgUserGameMmr.objects.update_or_create(
            org_user=org_user, game_type=game, defaults={"mmr": mmr}
        )

    def _by_name(self, source: CandidateSource, **kwargs: Any) -> dict[str, Any]:
        return {r["username"]: r for r in self._rows(source, **kwargs)}


class OrgMmrSourceTest(_MmrBase):
    def test_uses_this_orgs_mmr_for_the_events_game(self) -> None:
        self._mmr(self.recipient, 4200)
        self._mmr(self.recipient, 9100, org=self.other_org)
        self._mmr(self.recipient, 1300, game=GameType.DEADLOCK)
        self.recipient.mmr = 7777
        self.recipient.save()
        row = self._by_name(CandidateSource.RECENT)["papi_recipient"]
        self.assertEqual(row["mmr"], 4200)

    def test_deadlock_event_reads_deadlock_mmr(self) -> None:
        self._mmr(self.recipient, 4200)
        self._mmr(self.recipient, 1300, game=GameType.DEADLOCK)
        self.event.game_type = GameType.DEADLOCK
        self.event.save()
        row = self._by_name(CandidateSource.RECENT)["papi_recipient"]
        self.assertEqual(row["mmr"], 1300)

    def test_missing_mmr_is_none(self) -> None:
        self.assertIsNone(
            self._by_name(CandidateSource.RECENT)["papi_recipient"]["mmr"]
        )
        self._mmr(self.recipient, 0)
        self.assertIsNone(
            self._by_name(CandidateSource.RECENT)["papi_recipient"]["mmr"]
        )

    def test_other_org_only_mmr_is_none(self) -> None:
        self._mmr(self.recipient, 9100, org=self.other_org)
        row = self._by_name(CandidateSource.RECENT)["papi_recipient"]
        self.assertIsNone(row["mmr"])


class MmrFilterTest(_MmrBase):
    def setUp(self) -> None:
        super().setUp()
        self.players: dict[str, CustomUser] = {}
        for name, mmr in (("low", 2000), ("edge", 3000), ("high", 5000)):
            user = self._user(f"mmr_{name}")
            self._signup(user, self.completed_event, days_ago=1)
            self._mmr(user, mmr)
            self.players[name] = user
        self.unknown = self._user("mmr_unknown")
        self._signup(self.unknown, self.completed_event, days_ago=1)
        self.foreign = self._user("mmr_foreign")
        self._signup(self.foreign, self.completed_event, days_ago=1)
        self._mmr(self.foreign, 6000, org=self.other_org)

    def _names(self, **kwargs: Any) -> set[str]:
        return {
            n
            for n in self._by_name(CandidateSource.ACTIVE, **kwargs)
            if n.startswith("mmr_")
        }

    def test_no_bounds_lists_everyone_with_unknowns(self) -> None:
        self.assertEqual(
            self._names(),
            {"mmr_low", "mmr_edge", "mmr_high", "mmr_unknown", "mmr_foreign"},
        )

    def test_min_is_inclusive_and_drops_unknown(self) -> None:
        self.assertEqual(self._names(min_mmr=3000), {"mmr_edge", "mmr_high"})
        self.assertEqual(self._names(min_mmr=3001), {"mmr_high"})

    def test_max_is_inclusive(self) -> None:
        self.assertEqual(self._names(max_mmr=3000), {"mmr_low", "mmr_edge"})

    def test_range(self) -> None:
        self.assertEqual(self._names(min_mmr=2500, max_mmr=4000), {"mmr_edge"})

    def test_min_zero_still_drops_unknown(self) -> None:
        self.assertEqual(self._names(min_mmr=0), {"mmr_low", "mmr_edge", "mmr_high"})


class DiscordCapTest(_MmrBase):
    def setUp(self) -> None:
        super().setUp()
        self.members = [
            guild_member(f"99100{i}", f"joiner{i}", joined=self.now - timedelta(days=1))
            for i in range(5)
        ]
        self.oldest = self._user("cap_oldest")
        self._mmr(self.oldest, 4500)
        self.members.append(
            guild_member(
                self.oldest.discordId or "",
                "cap_oldest_dc",
                joined=self.now - timedelta(days=20),
                nick="Deep Cut",
            )
        )

    def test_unfiltered_list_is_capped(self) -> None:
        with patch(FETCH, return_value=self.members), patch(CAP, 3):
            rows = self._rows(CandidateSource.DISCORD, days=30)
        self.assertEqual(len(rows), 3)
        self.assertNotIn(self.oldest.pk, [r["user_pk"] for r in rows])

    def test_mmr_filter_runs_before_cap(self) -> None:
        with patch(FETCH, return_value=self.members), patch(CAP, 3):
            rows = self._rows(CandidateSource.DISCORD, days=30, min_mmr=4000)
        self.assertEqual([r["user_pk"] for r in rows], [self.oldest.pk])
        self.assertEqual(rows[0]["mmr"], 4500)

    def test_search_runs_before_cap(self) -> None:
        with patch(FETCH, return_value=self.members), patch(CAP, 3):
            rows = self._rows(CandidateSource.DISCORD, days=30, q="cap_oldest")
        self.assertEqual([r["user_pk"] for r in rows], [self.oldest.pk])

    def test_unlinked_members_excluded_by_mmr_bound(self) -> None:
        with patch(FETCH, return_value=self.members):
            rows = self._rows(CandidateSource.DISCORD, days=30, max_mmr=20000)
        self.assertTrue(all(r["user_pk"] is not None for r in rows))

    def test_lookup_by_user_ignores_cap(self) -> None:
        with patch(FETCH, return_value=self.members), patch(CAP, 3):
            rows = candidates(
                self.org,
                self.event,
                n=3,
                sender=self.sender,
                source=CandidateSource.DISCORD,
                days=90,
                hide_signed_up=False,
                hide_messaged=False,
                user_pk=self.oldest.pk,
            )
        self.assertEqual([r["user_pk"] for r in rows], [self.oldest.pk])


class MmrApiTest(_MmrBase):
    def test_bounds_pass_through_and_echo_game(self) -> None:
        self._mmr(self.recipient, 4200)
        response = self.request(
            "promoter",
            "get",
            self.candidates_url(),
            {"source": "recent", "min_mmr": 4200, "max_mmr": 5000},
        )
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(
            (body["min_mmr"], body["max_mmr"], body["game_type"]),
            (4200, 5000, GameType.DOTA2),
        )
        self.assertEqual([r["mmr"] for r in body["rows"]], [4200])
        response = self.request(
            "promoter", "get", self.candidates_url(), {"min_mmr": 4201}
        )
        self.assertEqual(response.json()["rows"], [])

    def test_mmr_edit_is_seen_on_next_read(self) -> None:
        self.request("promoter", "get", self.candidates_url())
        org_user = OrgUser.objects.get(user=self.recipient, organization=self.org)
        set_org_mmr(org_user, GameType.DOTA2, 3900, mark_verified=False)
        body = self.request("promoter", "get", self.candidates_url()).json()
        self.assertEqual(body["rows"][0]["mmr"], 3900)

    def test_unbounded_echoes_null(self) -> None:
        body = self.request("promoter", "get", self.candidates_url()).json()
        self.assertEqual((body["min_mmr"], body["max_mmr"]), (None, None))
        self.assertIsNone(body["rows"][0]["mmr"])

    def test_invalid_bounds_400(self) -> None:
        for params in (
            {"min_mmr": -1},
            {"min_mmr": "lots"},
            {"max_mmr": 20001},
            {"min_mmr": 5000, "max_mmr": 4000},
        ):
            response = self.request("promoter", "get", self.candidates_url(), params)
            self.assertEqual(response.status_code, 400, params)

    def test_discord_filter_creates_no_accounts(self) -> None:
        members = [guild_member("991900", "ghost", joined=self.now - timedelta(days=1))]
        before = CustomUser.objects.count()
        with patch(FETCH, return_value=members):
            for params in ({}, {"min_mmr": 100}):
                response = self.request(
                    "promoter",
                    "get",
                    self.candidates_url(),
                    {"source": "discord", **params},
                )
                self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(CustomUser.objects.count(), before)

    def test_outsiders_and_members_still_denied(self) -> None:
        for role in ("member", "outsider"):
            response = self.request(role, "get", self.candidates_url(), {"min_mmr": 1})
            self.assertEqual(response.status_code, 403)
