from unittest.mock import patch

from django.db.models import prefetch_related_objects
from django.test import TestCase, override_settings
from django.utils import timezone
from structlog.testing import capture_logs

from app.models import CustomUser, GameType, Tournament
from events.models import Event
from league.models import League, LeagueUser
from org.mmr import (
    DEFAULT_GAME,
    LEAGUE_GAME,
    OrgMmrError,
    bulk_set_org_mmrs,
    game_for_event,
    game_for_tournament,
    game_mmrs_prefetch,
    get_org_mmr,
    get_org_mmrs,
    merge_org_mmrs,
    org_mmr_for,
    org_mmr_map,
    resolve_game_type,
    set_org_mmr,
)
from org.models import Organization, OrgUser, OrgUserGameMmr
from tests.populate.utils import ensure_league_user, ensure_org_user

DOTA = GameType.DOTA2
DL = GameType.DEADLOCK


def rows(org_user: OrgUser) -> dict[int, int]:
    return dict(
        OrgUserGameMmr.objects.filter(org_user=org_user).values_list("game_type", "mmr")
    )


def events_named(logs: list[dict], name: str) -> list[dict]:
    return [entry for entry in logs if entry.get("event") == name]


class OrgMmrHelperBase(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Helper Org A")
        self.org_b = Organization.objects.create(name="Helper Org B")
        self.user = CustomUser.objects.create(username="helper_u")
        self.other = CustomUser.objects.create(username="helper_v")
        self.ou = OrgUser.objects.create(user=self.user, organization=self.org)
        self.ou_other = OrgUser.objects.create(user=self.other, organization=self.org)

    def prefetched(self, org_user: OrgUser) -> OrgUser:
        return OrgUser.objects.prefetch_related(game_mmrs_prefetch(fresh=False)).get(
            pk=org_user.pk
        )


class ResolveGameTypeTest(TestCase):
    def test_resolve_game_type_defaults(self) -> None:
        self.assertEqual(DEFAULT_GAME, DOTA)
        self.assertEqual(LEAGUE_GAME, DOTA)
        for value in (None, 0, 99):
            self.assertIs(resolve_game_type(value), GameType.DOTA2)
        self.assertIs(resolve_game_type(2), GameType.DEADLOCK)

    def test_game_for_tournament_and_event_none(self) -> None:
        self.assertIs(game_for_tournament(None), GameType.DOTA2)
        self.assertIs(game_for_event(None), GameType.DOTA2)
        self.assertIs(game_for_tournament(Tournament(game_type=DL)), GameType.DEADLOCK)
        self.assertIs(game_for_event(Event(game_type=DL)), GameType.DEADLOCK)
        self.assertIs(game_for_tournament(Tournament(game_type=DOTA)), GameType.DOTA2)


class ReadHelpersTest(OrgMmrHelperBase):
    def test_get_org_mmr_prefetched_missing_row_is_zero(self) -> None:
        OrgUserGameMmr.objects.create(org_user=self.ou, game_type=DOTA, mmr=4000)
        ou = self.prefetched(self.ou)
        with self.assertNumQueries(0):
            self.assertEqual(get_org_mmr(ou, DOTA), 4000)
            self.assertEqual(get_org_mmr(ou, DL), 0)
            self.assertEqual(get_org_mmrs(ou), {1: 4000, 2: 0})

    def test_get_org_mmrs_is_memoized(self) -> None:
        OrgUserGameMmr.objects.create(org_user=self.ou, game_type=DL, mmr=2500)
        ou = self.prefetched(self.ou)
        first = get_org_mmrs(ou)
        self.assertEqual(ou._org_mmrs_memo, {1: 0, 2: 2500})
        first[2] = 1
        self.assertEqual(get_org_mmrs(ou), {1: 0, 2: 2500})

    @override_settings(RUNNING_TESTS=True)
    def test_unprefetched_read_raises_under_tests(self) -> None:
        ou = OrgUser.objects.get(pk=self.ou.pk)
        with self.assertRaises(AssertionError):
            get_org_mmr(ou, DOTA)
        with self.assertRaises(AssertionError):
            get_org_mmrs(ou)

    @override_settings(RUNNING_TESTS=False)
    def test_unprefetched_read_warns_outside_tests(self) -> None:
        OrgUserGameMmr.objects.create(org_user=self.ou, game_type=DL, mmr=2500)
        ou = OrgUser.objects.get(pk=self.ou.pk)
        with capture_logs() as logs:
            self.assertEqual(get_org_mmr(ou, DL), 2500)
        warned = events_named(logs, "org_mmr_unprefetched")
        self.assertEqual(len(warned), 1)
        self.assertEqual(warned[0]["log_level"], "warning")
        self.assertEqual(warned[0]["system"], "org")
        self.assertEqual(warned[0]["subsystem"], "mmr")
        self.assertEqual(warned[0]["org_user_id"], self.ou.pk)

    def test_get_org_mmr_none_org_user(self) -> None:
        with self.assertNumQueries(0):
            self.assertEqual(get_org_mmr(None, DOTA), 0)
            self.assertEqual(get_org_mmrs(None), {1: 0, 2: 0})

    def test_org_mmr_map_scoped_to_org_and_game(self) -> None:
        ou_b = OrgUser.objects.create(user=self.user, organization=self.org_b)
        OrgUserGameMmr.objects.create(org_user=self.ou, game_type=DL, mmr=2500)
        OrgUserGameMmr.objects.create(org_user=self.ou, game_type=DOTA, mmr=4000)
        OrgUserGameMmr.objects.create(org_user=ou_b, game_type=DL, mmr=900)
        with self.assertNumQueries(1):
            result = org_mmr_map(self.org.id, [self.user.id, self.other.id], DL)
        self.assertEqual(result, {self.user.id: 2500})
        self.assertEqual(
            org_mmr_map(self.org_b.id, [self.user.id], DL), {self.user.id: 900}
        )
        self.assertEqual(org_mmr_map(self.org_b.id, [self.user.id], DOTA), {})

    def test_org_mmr_map_empty_ids_no_query(self) -> None:
        with self.assertNumQueries(0):
            self.assertEqual(org_mmr_map(self.org.id, [], DOTA), {})

    def test_org_mmr_for_one_query_no_warning(self) -> None:
        OrgUserGameMmr.objects.create(org_user=self.ou, game_type=DL, mmr=2500)
        with capture_logs() as logs, self.assertNumQueries(1):
            self.assertEqual(org_mmr_for(self.org.id, self.user.id, DL), 2500)
        self.assertEqual(events_named(logs, "org_mmr_unprefetched"), [])
        self.assertEqual(org_mmr_for(self.org.id, self.user.id, DOTA), 0)
        self.assertEqual(org_mmr_for(self.org_b.id, self.user.id, DL), 0)

    def test_game_mmrs_prefetch_fresh_uses_nocache(self) -> None:
        fresh_profile = game_mmrs_prefetch(fresh=True).queryset._cacheprofile
        cached_profile = game_mmrs_prefetch(fresh=False).queryset._cacheprofile
        self.assertEqual(fresh_profile["ops"], set())
        self.assertIn("fetch", cached_profile["ops"])
        self.assertEqual(game_mmrs_prefetch(fresh=True).prefetch_through, "game_mmrs")


class SetOrgMmrTest(OrgMmrHelperBase):
    def reload(self) -> OrgUser:
        return OrgUser.objects.get(pk=self.ou.pk)

    def test_set_org_mmr_dota_sets_flags_any_value(self) -> None:
        for value in (4000, 0, None):
            OrgUser.objects.filter(pk=self.ou.pk).update(
                has_active_dota_mmr=False, dota_mmr_last_verified=None
            )
            ou = self.reload()
            set_org_mmr(ou, DOTA, value, mark_verified=True)
            fresh = self.reload()
            self.assertTrue(fresh.has_active_dota_mmr, value)
            self.assertIsNotNone(fresh.dota_mmr_last_verified, value)
            expected = {DOTA: value} if value else {}
            self.assertEqual(rows(self.ou), expected)

    def test_set_org_mmr_returns_row_or_none(self) -> None:
        row = set_org_mmr(self.ou, DL, 2500, mark_verified=False)
        self.assertIsInstance(row, OrgUserGameMmr)
        self.assertEqual(row.mmr, 2500)
        self.assertIsNone(set_org_mmr(self.ou, DL, None, mark_verified=False))
        self.assertEqual(rows(self.ou), {})

    def test_set_org_mmr_deadlock_never_sets_flags(self) -> None:
        set_org_mmr(self.ou, DL, 2500, mark_verified=True)
        fresh = self.reload()
        self.assertFalse(fresh.has_active_dota_mmr)
        self.assertIsNone(fresh.dota_mmr_last_verified)
        self.assertEqual(rows(self.ou), {DL: 2500})

    def test_set_org_mmr_mark_verified_false_leaves_flags(self) -> None:
        set_org_mmr(self.ou, DOTA, 4000, mark_verified=False)
        fresh = self.reload()
        self.assertFalse(fresh.has_active_dota_mmr)
        self.assertIsNone(fresh.dota_mmr_last_verified)
        self.assertEqual(rows(self.ou), {DOTA: 4000})

    def test_set_org_mmr_requires_mark_verified(self) -> None:
        with self.assertRaises(TypeError):
            set_org_mmr(self.ou, DOTA, 4000)  # type: ignore[call-arg]
        self.assertEqual(rows(self.ou), {})

    def test_set_org_mmr_validation(self) -> None:
        for game, value in ((99, 4000), (DOTA, 20001), (DOTA, -1), (DL, True)):
            with self.assertRaises(OrgMmrError):
                set_org_mmr(self.ou, game, value, mark_verified=True)
        self.assertEqual(rows(self.ou), {})
        self.assertFalse(self.reload().has_active_dota_mmr)
        set_org_mmr(self.ou, DOTA, 20000, mark_verified=False)
        self.assertEqual(rows(self.ou), {DOTA: 20000})

    def test_set_org_mmr_drops_prefetch_and_memo(self) -> None:
        OrgUserGameMmr.objects.create(org_user=self.ou, game_type=DOTA, mmr=4000)
        ou = self.prefetched(self.ou)
        self.assertEqual(get_org_mmr(ou, DOTA), 4000)
        self.assertEqual(get_org_mmrs(ou)[DOTA], 4000)
        set_org_mmr(ou, DOTA, 4500, mark_verified=False)
        self.assertNotIn("game_mmrs", ou._prefetched_objects_cache)
        self.assertFalse(hasattr(ou, "_org_mmrs_memo"))
        prefetch_related_objects([ou], game_mmrs_prefetch(fresh=True))
        self.assertEqual(get_org_mmr(ou, DOTA), 4500)
        self.assertEqual(get_org_mmrs(ou)[DOTA], 4500)

    def test_set_org_mmr_logs(self) -> None:
        OrgUserGameMmr.objects.create(org_user=self.ou, game_type=DL, mmr=1000)
        with capture_logs() as logs:
            set_org_mmr(self.ou, DL, 2500, mark_verified=False)
        entries = events_named(logs, "org_mmr_set")
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry["system"], "org")
        self.assertEqual(entry["subsystem"], "mmr")
        self.assertEqual(entry["org_user_id"], self.ou.pk)
        self.assertEqual(entry["game_type"], DL)
        self.assertEqual(entry["old_mmr"], 1000)
        self.assertEqual(entry["new_mmr"], 2500)

    def test_set_org_mmr_invalidates_all_user_tournaments(self) -> None:
        league_b = League.objects.create(organization=self.org_b, name="B League")
        event_tournament = Tournament.objects.create(
            name="Event Cup", date_played=timezone.now(), league=None
        )
        other_org_tournament = Tournament.objects.create(
            name="B Cup", date_played=timezone.now(), league=league_b
        )
        unrelated = Tournament.objects.create(
            name="Unrelated", date_played=timezone.now()
        )
        event_tournament.users.add(self.user)
        other_org_tournament.users.add(self.user)
        with patch("org.mmr.invalidate_obj") as invalidate:
            with self.captureOnCommitCallbacks(execute=True):
                set_org_mmr(self.ou, DL, 2500, mark_verified=False)
                invalidate.assert_not_called()
        invalidated = {call.args[0] for call in invalidate.call_args_list}
        self.assertIn(event_tournament, invalidated)
        self.assertIn(other_org_tournament, invalidated)
        self.assertNotIn(unrelated, invalidated)


class MergeOrgMmrsTest(OrgMmrHelperBase):
    def test_merge_org_mmrs(self) -> None:
        loser = self.ou_other
        keeper = self.ou
        OrgUser.objects.filter(pk=keeper.pk).update(has_active_dota_mmr=False)
        OrgUserGameMmr.objects.create(org_user=loser, game_type=DOTA, mmr=25000)
        OrgUserGameMmr.objects.create(org_user=loser, game_type=DL, mmr=1200)
        OrgUserGameMmr.objects.create(org_user=keeper, game_type=DOTA, mmr=4000)
        with capture_logs() as logs:
            merge_org_mmrs(loser, keeper)
        self.assertEqual(rows(keeper), {DOTA: 25000, DL: 1200})
        fresh = OrgUser.objects.get(pk=keeper.pk)
        self.assertFalse(fresh.has_active_dota_mmr)
        self.assertIsNone(fresh.dota_mmr_last_verified)
        entries = events_named(logs, "org_mmr_merged")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["system"], "org")
        self.assertEqual(entries[0]["subsystem"], "mmr")

    def test_merge_keeps_keeper_only_game_and_higher_keeper_value(self) -> None:
        loser = self.ou_other
        keeper = self.ou
        OrgUserGameMmr.objects.create(org_user=loser, game_type=DOTA, mmr=3000)
        OrgUserGameMmr.objects.create(org_user=keeper, game_type=DOTA, mmr=4000)
        OrgUserGameMmr.objects.create(org_user=keeper, game_type=DL, mmr=900)
        merge_org_mmrs(loser, keeper)
        self.assertEqual(rows(keeper), {DOTA: 4000, DL: 900})

    def test_merge_without_loser_rows_is_one_query(self) -> None:
        OrgUserGameMmr.objects.create(org_user=self.ou, game_type=DOTA, mmr=4000)
        with self.assertNumQueries(1), capture_logs() as logs:
            merge_org_mmrs(self.ou_other, self.ou)
        self.assertEqual(events_named(logs, "org_mmr_merged"), [])
        self.assertEqual(rows(self.ou), {DOTA: 4000})


class BulkSetOrgMmrsTest(OrgMmrHelperBase):
    def setUp(self) -> None:
        super().setUp()
        self.third = CustomUser.objects.create(username="helper_w")
        self.ou_third = OrgUser.objects.create(user=self.third, organization=self.org)

    def test_bulk_set_rejects_out_of_range_before_writing(self) -> None:
        OrgUserGameMmr.objects.create(org_user=self.ou_other, game_type=DL, mmr=700)
        values = {self.user.id: 3000, self.other.id: None, self.third.id: 25000}
        with self.assertRaises(OrgMmrError) as ctx:
            bulk_set_org_mmrs(self.org.id, DL, values)
        self.assertIn(str(self.third.id), str(ctx.exception))
        self.assertEqual(rows(self.ou), {})
        self.assertEqual(rows(self.ou_other), {DL: 700})

    def test_bulk_set_rejects_unknown_game(self) -> None:
        with self.assertRaises(OrgMmrError):
            bulk_set_org_mmrs(self.org.id, 99, {self.user.id: 3000})

    def test_bulk_set_org_mmrs(self) -> None:
        OrgUserGameMmr.objects.create(org_user=self.ou, game_type=DL, mmr=100)
        OrgUserGameMmr.objects.create(org_user=self.ou_other, game_type=DL, mmr=700)
        OrgUserGameMmr.objects.create(org_user=self.ou_other, game_type=DOTA, mmr=5000)
        event_tournament = Tournament.objects.create(
            name="Bulk Event Cup", date_played=timezone.now(), league=None
        )
        event_tournament.users.add(self.user)
        with (
            patch("org.mmr.invalidate_obj") as invalidate,
            patch("org.mmr.invalidate_model") as invalidate_model,
            capture_logs() as logs,
        ):
            with self.captureOnCommitCallbacks(execute=True):
                bulk_set_org_mmrs(
                    self.org.id, DL, {self.user.id: 3000, self.other.id: None}
                )
        self.assertEqual(rows(self.ou), {DL: 3000})
        self.assertEqual(rows(self.ou_other), {DOTA: 5000})
        self.assertFalse(OrgUser.objects.get(pk=self.ou.pk).has_active_dota_mmr)
        invalidated = {call.args[0] for call in invalidate.call_args_list}
        self.assertIn(event_tournament, invalidated)
        self.assertIn(self.ou, invalidated)
        self.assertIn(self.ou_other, invalidated)
        invalidate_model.assert_called_once_with(OrgUserGameMmr)
        entries = events_named(logs, "org_mmr_set")
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["upserted"], 1)
        self.assertEqual(entries[0]["cleared"], 1)

    def test_bulk_set_rejects_user_without_membership(self) -> None:
        outsider = CustomUser.objects.create(username="helper_outsider")
        with self.assertRaises(OrgMmrError) as ctx:
            bulk_set_org_mmrs(self.org.id, DL, {outsider.id: 3000})
        self.assertIn(str(outsider.id), str(ctx.exception))


class EnsureOrgUserTest(TestCase):
    def setUp(self) -> None:
        self.org = Organization.objects.create(name="Ensure Org")
        self.league = League.objects.create(organization=self.org, name="Ensure League")
        self.user = CustomUser.objects.create(username="ensure_u")

    def test_ensure_org_user_writes_rows(self) -> None:
        with (
            patch("org.mmr.invalidate_obj") as invalidate,
            capture_logs() as logs,
        ):
            ou = ensure_org_user(self.user, self.org, mmr=4000, game_mmrs={DL: 2500})
        self.assertEqual(rows(ou), {DOTA: 4000, DL: 2500})
        self.assertEqual(OrgUser.objects.get(pk=ou.pk).mmr, 4000)
        self.assertEqual(events_named(logs, "org_mmr_set"), [])
        invalidate.assert_not_called()

    def test_ensure_org_user_none_preserves_rows(self) -> None:
        ou = ensure_org_user(self.user, self.org, mmr=4000, game_mmrs={DL: 2500})
        ensure_org_user(self.user, self.org)
        ensure_org_user(self.user, self.org, game_mmrs={})
        self.assertEqual(rows(ou), {DOTA: 4000, DL: 2500})
        self.assertEqual(OrgUser.objects.get(pk=ou.pk).mmr, 4000)
        league_user = ensure_league_user(self.user, ou, self.league)
        self.assertEqual(league_user.mmr, 4000)
        ensure_org_user(self.user, self.org, mmr=0)
        self.assertEqual(rows(ou), {DL: 2500})
        self.assertEqual(OrgUser.objects.get(pk=ou.pk).mmr, 0)
        ensure_org_user(self.user, self.org, game_mmrs={DL: 0})
        self.assertEqual(rows(ou), {})

    def test_ensure_org_user_rejects_out_of_range(self) -> None:
        with self.assertRaises(OrgMmrError):
            ensure_org_user(self.user, self.org, game_mmrs={DL: 30000})

    def test_ensure_league_user_seeds_dota(self) -> None:
        ou = ensure_org_user(self.user, self.org, mmr=4000, game_mmrs={DL: 2500})
        OrgUser.objects.filter(pk=ou.pk).update(mmr=1)
        league_user = ensure_league_user(
            self.user, OrgUser.objects.get(pk=ou.pk), self.league
        )
        self.assertEqual(league_user.mmr, 4000)
        self.assertEqual(LeagueUser.objects.get(pk=league_user.pk).mmr, 4000)
