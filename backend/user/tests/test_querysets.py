from typing import Any

from django.db.models import QuerySet
from django.test import SimpleTestCase

from app.models import CustomUser
from events.models import EventSignup, RepeaterSubscription
from league.models import LeagueUser
from org.models import OrgUser
from steam.models import LeaguePlayerStats
from user.querysets import with_user_profiles

_DOTA_CHAIN: dict[str, Any] = {"base_profile": {"dota_user_profile": {"positions": {}}}}


class WithUserProfilesTests(SimpleTestCase):
    def assert_shape(self, qs: QuerySet[Any], expected: dict[str, Any]) -> None:
        self.assertEqual(qs.query.select_related, expected)
        self.assertEqual(qs._cacheprofile["ops"], set())

    def test_custom_user_base_profile(self) -> None:
        self.assert_shape(
            with_user_profiles(CustomUser.objects.all()), {"base_profile": {}}
        )

    def test_custom_user_dota(self) -> None:
        self.assert_shape(
            with_user_profiles(CustomUser.objects.all(), dota=True), _DOTA_CHAIN
        )

    def test_org_user_dota(self) -> None:
        self.assert_shape(
            with_user_profiles(OrgUser.objects.all(), "user", dota=True),
            {"user": _DOTA_CHAIN},
        )

    def test_league_user_dota(self) -> None:
        self.assert_shape(
            with_user_profiles(LeagueUser.objects.all(), "user", dota=True),
            {"user": _DOTA_CHAIN},
        )

    def test_event_signup_keeps_extra_joins(self) -> None:
        self.assert_shape(
            with_user_profiles(
                EventSignup.objects.select_related("event", "event_team"), "user"
            ),
            {"event": {}, "event_team": {}, "user": {"base_profile": {}}},
        )

    def test_league_player_stats(self) -> None:
        self.assert_shape(
            with_user_profiles(LeaguePlayerStats.objects.all(), "user"),
            {"user": {"base_profile": {}}},
        )

    def test_repeater_subscription(self) -> None:
        self.assert_shape(
            with_user_profiles(RepeaterSubscription.objects.all(), "user"),
            {"user": {"base_profile": {}}},
        )
