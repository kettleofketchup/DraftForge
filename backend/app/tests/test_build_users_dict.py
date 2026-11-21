from django.test import TransactionTestCase
from django.utils import timezone

from app.models import CustomUser, GameType, League, Organization, Tournament
from app.serializers import (
    TournamentSerializer,
    _build_users_dict,
    _serialize_users_with_mmr,
)
from events.models import Event
from events.services import create_tournament_for_event
from league.models import LeagueUser
from org.mmr import set_org_mmr
from org.models import OrgUser
from tests.populate.utils import ensure_org_user

# Hardcoded pre-change ground-truth key sets (from reading OrgUserSerializer /
# TournamentUserSerializer). The shape-parity assertions below ALSO diff against
# the untouched _serialize_users_with_mmr at runtime, so any drift fails loudly.
ORG_ENTRY_KEYS = {
    "orgUserPk",
    "pk",
    "username",
    "nickname",
    "guildNickname",
    "discordNickname",
    "avatar",
    "discordId",
    "positions",
    "steam_account_id",
    "avatarUrl",
    "mmr",
    "mmr_game_type",
    "league_mmr",
}
NONORG_ENTRY_KEYS = {
    "pk",
    "username",
    "nickname",
    "avatar",
    "discordId",
    "discordNickname",
    "positions",
    "steam_account_id",
    "avatarUrl",
}


class BuildUsersDictOrgTests(TransactionTestCase):
    def setUp(self) -> None:
        self.owner = CustomUser.objects.create_user(username="owner", password="x")
        self.org = Organization.objects.create(name="Org", owner=self.owner)
        self.league = League.objects.create(
            name="Lg", organization=self.org, steam_league_id=12345
        )
        self.tournament = Tournament.objects.create(
            name="T",
            league=self.league,
            tournament_type="double_elimination",
            date_played=timezone.now(),
        )
        self.member = CustomUser.objects.create(username="member", nickname="Member")
        self.tournament.users.add(self.member)

        ou = ensure_org_user(self.member, self.org, mmr=4200)
        LeagueUser.objects.update_or_create(
            user=self.member,
            org_user=ou,
            league=self.league,
            defaults={"mmr": 3100},
        )

    def test_org_entry_has_core_and_mmr(self) -> None:
        entry = _build_users_dict(self.tournament)[self.member.pk]
        # core half (cached per-user)
        assert entry["nickname"] == "Member"
        assert "positions" in entry
        # contextual MMR half (merged per-request)
        assert entry["mmr"] == 4200
        assert entry["league_mmr"] == 3100
        assert "orgUserPk" in entry

    def test_org_shape_parity(self) -> None:
        entry = _build_users_dict(self.tournament)[self.member.pk]
        ref = _serialize_users_with_mmr(
            CustomUser.objects.filter(pk=self.member.pk), self.tournament
        )[0]
        # key-set parity vs the untouched serializer AND the hardcoded baseline
        assert set(entry.keys()) == set(ref.keys())
        assert set(entry.keys()) == ORG_ENTRY_KEYS
        # value parity on every shared key (byte-identical data)
        for k in ref:
            assert entry[k] == ref[k], (k, entry[k], ref[k])

    def test_org_entry_carries_server_and_global_names(self) -> None:
        OrgUser.objects.filter(user=self.member, organization=self.org).update(
            guild_nickname="DragonClaw"
        )
        CustomUser.objects.filter(pk=self.member.pk).update(
            discordNickname="GwaihirTheWindlord"
        )
        entry = _build_users_dict(self.tournament, fresh=True)[self.member.pk]
        assert entry["guildNickname"] == "DragonClaw"
        assert entry["discordNickname"] == "GwaihirTheWindlord"

    def test_nickname_edit_reflected(self) -> None:
        _build_users_dict(self.tournament)  # warm core cache
        self.member.nickname = "Renamed"
        entry = _build_users_dict(self.tournament)[self.member.pk]
        assert entry["nickname"] == "Renamed"

    def test_mmr_change_reflected(self) -> None:
        _build_users_dict(self.tournament)  # warm
        ou = OrgUser.objects.get(user=self.member, organization=self.org)
        set_org_mmr(ou, GameType.DOTA2, 5555, mark_verified=False)
        entry = _build_users_dict(self.tournament)[self.member.pk]
        assert entry["mmr"] == 5555


class BuildUsersDictNonOrgTests(TransactionTestCase):
    def setUp(self) -> None:
        self.tournament = Tournament.objects.create(
            name="NoOrg",
            tournament_type="double_elimination",
            date_played=timezone.now(),
        )
        self.member = CustomUser.objects.create(username="solo", nickname="Solo")
        self.tournament.users.add(self.member)

    def test_nonorg_no_mmr_shape_parity(self) -> None:
        entry = _build_users_dict(self.tournament)[self.member.pk]
        assert "mmr" not in entry and "league_mmr" not in entry
        ref = _serialize_users_with_mmr(
            CustomUser.objects.filter(pk=self.member.pk), self.tournament
        )[0]
        assert set(entry.keys()) == set(ref.keys())
        assert set(entry.keys()) == NONORG_ENTRY_KEYS
        for k in ref:
            assert entry[k] == ref[k], (k, entry[k], ref[k])


class BuildUsersDictLeaguelessEventTests(TransactionTestCase):
    """Event-spawned tournaments with no league inherit the event's org."""

    def setUp(self) -> None:
        self.owner = CustomUser.objects.create_user(username="owner", password="x")
        self.org = Organization.objects.create(name="Org", owner=self.owner)
        event = Event.objects.create(
            name="Weekly",
            organization=self.org,
            scheduled_at=timezone.now(),
            timezone="UTC",
        )
        self.tournament = create_tournament_for_event(event)
        assert self.tournament.league is None
        self.member = CustomUser.objects.create(username="member", nickname="Member")
        self.tournament.users.add(self.member)
        ensure_org_user(self.member, self.org, mmr=4200)

    def test_entry_carries_event_org_mmr(self) -> None:
        entry = _build_users_dict(self.tournament)[self.member.pk]
        assert entry["mmr"] == 4200
        assert entry["league_mmr"] is None
        assert "orgUserPk" in entry
        ref = _serialize_users_with_mmr(
            CustomUser.objects.filter(pk=self.member.pk), self.tournament
        )[0]
        assert set(entry.keys()) == set(ref.keys()) == ORG_ENTRY_KEYS
        for k in ref:
            assert entry[k] == ref[k], (k, entry[k], ref[k])

    def test_organization_pk_falls_back_to_event_org(self) -> None:
        data = TournamentSerializer(self.tournament).data
        assert data["organization_pk"] == self.org.pk
        assert data["league_pk"] is None
