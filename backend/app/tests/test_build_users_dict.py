from django.test import TransactionTestCase
from django.utils import timezone

from app.models import CustomUser, League, Organization, Tournament
from app.serializers import _build_users_dict, _serialize_users_with_mmr

# Hardcoded pre-change ground-truth key sets (from reading OrgUserSerializer /
# TournamentUserSerializer). The shape-parity assertions below ALSO diff against
# the untouched _serialize_users_with_mmr at runtime, so any drift fails loudly.
ORG_ENTRY_KEYS = {
    "orgUserPk",
    "pk",
    "username",
    "nickname",
    "guildNickname",
    "avatar",
    "discordId",
    "positions",
    "steam_account_id",
    "avatarUrl",
    "mmr",
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

        from league.models import LeagueUser
        from org.models import OrgUser

        # Adding the member to an org tournament auto-creates the OrgUser via
        # signal; update its MMR rather than create a duplicate.
        ou, _ = OrgUser.objects.update_or_create(
            user=self.member, organization=self.org, defaults={"mmr": 4200}
        )
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

    def test_nickname_edit_reflected(self) -> None:
        _build_users_dict(self.tournament)  # warm core cache
        self.member.nickname = "Renamed"
        entry = _build_users_dict(self.tournament)[self.member.pk]
        assert entry["nickname"] == "Renamed"

    def test_mmr_change_reflected(self) -> None:
        _build_users_dict(self.tournament)  # warm
        from org.models import OrgUser

        ou = OrgUser.objects.get(user=self.member, organization=self.org)
        ou.mmr = 5555
        ou.save()
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
