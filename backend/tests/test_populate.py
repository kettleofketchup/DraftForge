"""
Populate guard regression tests.

These tests assert invariants of the test-data populate pipeline that, if
broken, would silently invalidate Playwright auth fixtures and event-staff
permission specs.
"""

from datetime import timedelta

from django.contrib.sessions.backends.db import SessionStore
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIRequestFactory

from app.models import (
    CustomUser,
    Draft,
    DraftRound,
    League,
    Organization,
    Tournament,
)
from events.constants import EventState
from events.models import Event
from org.contributions.kinds import ContributionKind
from org.contributions.services import award_entry, set_point_value
from org.features import FeatureKey, org_has_feature, set_org_feature
from org.models import ContributionEntry, ContributionPointValue, OrgUser, PromoSend
from org.models_promotion import PromoTemplate
from org.promotion.recipients import candidates
from org.promotion.services import record_promo_send
from tests.data.leagues import EVENTS_LEAGUE
from tests.data.org_delete import ORG_DELETE_ORG
from tests.data.org_features import (
    FEATURES_LEAGUE,
    FEATURES_ORG,
    LOCKED_FEATURES_ORG,
    ORG_FEATURES_COMPLETED_EVENT_NAME,
    ORG_FEATURES_PLAYERS,
    ORG_FEATURES_ROLE_USERS,
    ORG_FEATURES_TEMPLATE_NAMES,
    ORG_FEATURES_TOURNAMENTS,
    ORG_FEATURES_UPCOMING_EVENT_NAME,
    PRIVATE_FEATURES_ORG,
)
from tests.data.organizations import AUTH_MATRIX_ORG, EVENTS_ORG
from tests.data.users import AUTH_MATRIX_ORG_PROMOTER_USER, EVENT_LEAGUE_STAFF_USER
from tests.helpers.tournament_config import TEST_TOURNAMENTS, populate_test_tournaments
from tests.populate.auth_matrix import populate_auth_matrix_data
from tests.populate.demo import (
    populate_demo_shuffle_draft_tournament,
    populate_demo_snake_draft_tournament,
)
from tests.populate.org_delete import populate_org_delete
from tests.populate.org_features import (
    populate_org_features_data,
    reset_org_features_data,
)
from tests.populate.organizations import populate_organizations_and_leagues
from tests.populate.shuffle_tie import populate_shuffle_tie_data
from tests.populate.users import populate_test_auth_users, populate_users
from tests.populate.utils import delete_ledger_for_users
from tests.test_auth import login_auth_matrix_org_promoter, reset_tournament_by_key
from tests.test_org_features import (
    login_org_features,
    org_features_data,
    reset_org_features,
)


class EventLeagueStaffIsolationTest(TestCase):
    """Regression guard: event_league_staff must be staff of league 7 only,
    never of org 7. Used by Playwright tests to assert league-staff-only
    access on event pages.
    """

    @classmethod
    def setUpTestData(cls):
        from tests.populate.events import populate_events_data
        from tests.populate.organizations import populate_organizations_and_leagues
        from tests.populate.users import populate_test_auth_users

        # Run populate dependencies in order. populate_events_data creates
        # league pk=7 and is responsible for the league.staff assignment.
        populate_organizations_and_leagues(force=True)
        populate_test_auth_users(force=True)
        populate_events_data(force=True)

    def test_event_league_staff_isolation(self):
        user = CustomUser.objects.get(pk=EVENT_LEAGUE_STAFF_USER.pk)
        league = League.objects.get(pk=EVENTS_LEAGUE.pk)
        org = Organization.objects.get(pk=EVENTS_ORG.pk)

        assert user in league.staff.all(), "Should be staff of league 7"
        assert user not in org.staff.all(), "MUST NOT be staff of org 7"
        assert user not in org.admins.all(), "MUST NOT be admin of org 7"


class PopulateBuiltDraftsAreUntimedTest(TestCase):
    @classmethod
    @override_settings(DISCORD_BOT_TOKEN=None, DEBUG=True)
    def setUpTestData(cls):
        populate_organizations_and_leagues(force=True)
        populate_users(force=True)
        populate_test_auth_users(force=True)
        populate_test_tournaments(force=True)
        populate_shuffle_tie_data(force=True)
        populate_demo_snake_draft_tournament(force=True)
        populate_demo_shuffle_draft_tournament(force=True)

    def test_every_populate_draft_without_opt_in_is_drafting_and_unarmed(self):
        checked = 0
        for draft in Draft.objects.select_related("tournament").all():
            if (
                not draft.draft_rounds.exists()
                or draft.tournament.get_draft_options().timer_enabled
            ):
                continue
            checked += 1
            finished = not draft.draft_rounds.filter(choice__isnull=True).exists()
            expected = "completed" if finished else "drafting"
            self.assertEqual(draft.state, expected, draft.tournament.name)
            self.assertFalse(
                DraftRound.objects.filter(
                    draft=draft, started_at__isnull=False
                ).exists(),
                draft.tournament.name,
            )
        self.assertGreaterEqual(checked, 6)


TIMER_KEYS: list[str] = [
    "draft_timer_ready",
    "draft_timer_countdown",
    "draft_timer_skip",
    "draft_timer_pause",
    "shuffle_timer_skip",
]


class PopulateTimerLobbiesTest(TestCase):
    @classmethod
    @override_settings(DISCORD_BOT_TOKEN=None, DEBUG=True)
    def setUpTestData(cls) -> None:
        populate_organizations_and_leagues(force=True)
        populate_users(force=True)
        populate_test_auth_users(force=True)
        populate_test_tournaments(force=True)
        populate_shuffle_tie_data(force=True)
        populate_demo_snake_draft_tournament(force=True)
        populate_demo_shuffle_draft_tournament(force=True)

    def test_only_the_five_timer_lobbies_are_pending_with_rounds(self) -> None:
        names = sorted(
            Draft.objects.filter(state="pending", draft_rounds__isnull=False)
            .distinct()
            .values_list("tournament__name", flat=True)
        )
        expected = sorted(c.name for c in TEST_TOURNAMENTS if c.key in TIMER_KEYS)
        self.assertEqual(len(expected), 5)
        self.assertEqual(names, expected)

    @override_settings(DEBUG=True)
    def test_reset_tournament_by_key_rebuilds_each_timer_lobby(self) -> None:
        factory = APIRequestFactory()
        for key in TIMER_KEYS:
            config = next(c for c in TEST_TOURNAMENTS if c.key == key)
            response = reset_tournament_by_key(
                factory.post(f"/api/tests/reset-tournament/{key}/"), key
            )
            self.assertEqual(response.status_code, 200, key)
            draft = Draft.objects.get(tournament__name=config.name)
            self.assertEqual(draft.state, "pending", key)
            opts = draft.tournament.get_draft_options(fresh=True)
            self.assertEqual(
                (opts.timer_enabled, opts.grace_time_ms, opts.reserve_time_ms),
                (True, config.grace_time_ms, config.reserve_time_ms),
                key,
            )


def _upcoming(org_pk: int = FEATURES_ORG.pk) -> Event:
    return Event.objects.nocache().get(
        organization_id=org_pk, name=ORG_FEATURES_UPCOMING_EVENT_NAME
    )


class OrgFeaturesPopulateTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        populate_org_features_data(force=True)

    def test_switches_match_the_seeded_state(self) -> None:
        for org_pk, unlocked in (
            (FEATURES_ORG.pk, True),
            (LOCKED_FEATURES_ORG.pk, False),
            (PRIVATE_FEATURES_ORG.pk, True),
        ):
            for key in FeatureKey:
                self.assertEqual(org_has_feature(org_pk, key), unlocked, (org_pk, key))
        privacy = dict(
            Organization.objects.filter(
                pk__in=[
                    FEATURES_ORG.pk,
                    LOCKED_FEATURES_ORG.pk,
                    PRIVATE_FEATURES_ORG.pk,
                ]
            ).values_list("pk", "members_private")
        )
        self.assertEqual(
            privacy,
            {
                FEATURES_ORG.pk: False,
                LOCKED_FEATURES_ORG.pk: False,
                PRIVATE_FEATURES_ORG.pk: True,
            },
        )

    def test_roles(self) -> None:
        org = Organization.objects.get(pk=FEATURES_ORG.pk)
        roles = ORG_FEATURES_ROLE_USERS
        self.assertEqual(org.owner_id, roles["owner"].pk)
        self.assertIn(roles["admin"].pk, org.admins.values_list("pk", flat=True))
        self.assertIn(roles["staff"].pk, org.staff.values_list("pk", flat=True))
        self.assertEqual(
            list(org.promoters.values_list("pk", flat=True)), [roles["promoter"].pk]
        )
        self.assertTrue(
            OrgUser.objects.filter(
                organization=org, user_id=roles["member"].pk
            ).exists()
        )
        self.assertFalse(
            OrgUser.objects.filter(
                organization=org, user_id=roles["outsider"].pk
            ).exists()
        )
        locked = Organization.objects.get(pk=LOCKED_FEATURES_ORG.pk)
        self.assertIn(
            roles["locked_admin"].pk, locked.admins.values_list("pk", flat=True)
        )
        private = Organization.objects.get(pk=PRIVATE_FEATURES_ORG.pk)
        self.assertTrue(
            OrgUser.objects.filter(
                organization=private, user_id=roles["private_member"].pk
            ).exists()
        )

    def test_upcoming_event_pool_has_candidates(self) -> None:
        promoter = CustomUser.objects.get(pk=ORG_FEATURES_ROLE_USERS["promoter"].pk)
        org = Organization.objects.get(pk=FEATURES_ORG.pk)
        rows = candidates(org, _upcoming(), n=3, sender=promoter)
        self.assertGreaterEqual(len(rows), 5)
        self.assertTrue(all(r["discordId"] for r in rows))

    def test_completed_event_has_staff_and_ledger(self) -> None:
        event = Event.objects.nocache().get(
            organization_id=FEATURES_ORG.pk, name=ORG_FEATURES_COMPLETED_EVENT_NAME
        )
        self.assertEqual(event.state, EventState.COMPLETED)
        self.assertEqual(event.host_id, ORG_FEATURES_ROLE_USERS["staff"].pk)
        self.assertEqual(
            list(event.helpers.values_list("pk", flat=True)),
            [ORG_FEATURES_ROLE_USERS["promoter"].pk],
        )
        self.assertIsNotNone(event.contributions_awarded_at)
        kinds = set(
            ContributionEntry.objects.nocache()
            .filter(event=event)
            .values_list("org_user__user_id", "kind")
        )
        self.assertEqual(
            kinds,
            {
                (
                    ORG_FEATURES_ROLE_USERS["staff"].pk,
                    ContributionKind.EVENT_HOST.value,
                ),
                (
                    ORG_FEATURES_ROLE_USERS["promoter"].pk,
                    ContributionKind.EVENT_HELPER.value,
                ),
            },
        )

    def test_private_org_has_member_ledger_rows(self) -> None:
        users = set(
            ContributionEntry.objects.nocache()
            .filter(organization_id=PRIVATE_FEATURES_ORG.pk)
            .values_list("org_user__user_id", flat=True)
        )
        self.assertIn(ORG_FEATURES_ROLE_USERS["private_member"].pk, users)
        self.assertGreaterEqual(len(users), 2)

    def test_templates(self) -> None:
        for org_pk in (FEATURES_ORG.pk, PRIVATE_FEATURES_ORG.pk):
            names = list(
                PromoTemplate.objects.filter(organization_id=org_pk)
                .order_by("name")
                .values_list("name", flat=True)
            )
            self.assertEqual(names, sorted(ORG_FEATURES_TEMPLATE_NAMES), org_pk)
        self.assertFalse(
            PromoTemplate.objects.filter(
                organization_id=LOCKED_FEATURES_ORG.pk
            ).exists()
        )

    def test_players_have_unique_discord_ids(self) -> None:
        ids = list(
            CustomUser.objects.filter(
                pk__in=[p.pk for p in ORG_FEATURES_PLAYERS]
            ).values_list("discordId", flat=True)
        )
        self.assertEqual(len(ids), 10)
        self.assertEqual(len(set(ids)), 10)
        self.assertTrue(all(ids))

    def test_reset_restores_the_seeded_state(self) -> None:
        org = Organization.objects.get(pk=FEATURES_ORG.pk)
        promoter = CustomUser.objects.get(pk=ORG_FEATURES_ROLE_USERS["promoter"].pk)
        admin = CustomUser.objects.get(pk=ORG_FEATURES_ROLE_USERS["admin"].pk)
        event = _upcoming()
        recipient = CustomUser.objects.get(
            pk=candidates(org, event, n=3, sender=promoter)[0]["user_pk"]
        )
        record_promo_send(
            sender=promoter, event=event, recipient=recipient, template=None, text="hi"
        )
        set_point_value(
            org, ContributionKind.PROMO_MESSAGE, 3, actor=admin, apply_to_past=True
        )
        set_org_feature(org, FeatureKey.PROMOTION, enabled=False, actor=admin)
        org.promoters.clear()
        PromoTemplate.objects.filter(organization=org).delete()
        outsider = CustomUser.objects.get(pk=ORG_FEATURES_ROLE_USERS["outsider"].pk)
        OrgUser.objects.create(user=outsider, organization=org)
        member_org_user_pk = (
            OrgUser.objects.nocache()
            .get(user_id=ORG_FEATURES_ROLE_USERS["member"].pk, organization=org)
            .pk
        )
        seeded_pk, _, _, seeded_players = ORG_FEATURES_TOURNAMENTS[0]
        seeded = Tournament.objects.get(pk=seeded_pk)
        seeded.users.add(outsider)
        Tournament.objects.filter(pk=seeded_pk).update(state="in_progress")
        stray = Tournament.objects.create(
            name="Stray",
            league_id=FEATURES_LEAGUE.pk,
            date_played=timezone.now() - timedelta(days=1),
            state="past",
        )
        Organization.objects.filter(pk=org.pk).update(timezone="Not/AZone", name="X")

        data = reset_org_features_data()

        self.assertFalse(PromoSend.objects.filter(organization=org).exists())
        self.assertFalse(
            ContributionPointValue.objects.filter(organization=org).exists()
        )
        self.assertTrue(org_has_feature(org, FeatureKey.PROMOTION))
        self.assertEqual(
            list(org.promoters.values_list("pk", flat=True)), [promoter.pk]
        )
        self.assertEqual(PromoTemplate.objects.filter(organization=org).count(), 2)
        self.assertFalse(Event.objects.filter(pk=event.pk).exists())
        self.assertEqual(data["events"]["upcoming"]["pk"], _upcoming().pk)
        self.assertFalse(
            ContributionEntry.objects.nocache()
            .filter(organization=org, kind=ContributionKind.PROMO_MESSAGE)
            .exists()
        )
        self.assertEqual(
            ContributionEntry.objects.nocache().filter(organization=org).count(), 2
        )
        self.assertFalse(
            OrgUser.objects.nocache().filter(user=outsider, organization=org).exists()
        )
        self.assertTrue(
            OrgUser.objects.nocache()
            .filter(
                pk=member_org_user_pk,
                user_id=ORG_FEATURES_ROLE_USERS["member"].pk,
                organization=org,
            )
            .exists()
        )
        self.assertFalse(Tournament.objects.nocache().filter(pk=stray.pk).exists())
        seeded = Tournament.objects.nocache().get(pk=seeded_pk)
        self.assertEqual(seeded.state, "past")
        self.assertEqual(
            set(seeded.users.values_list("pk", flat=True)),
            {p.pk for p in seeded_players},
        )
        self.assertEqual(
            Tournament.objects.nocache().filter(league_id=FEATURES_LEAGUE.pk).count(),
            len(ORG_FEATURES_TOURNAMENTS),
        )
        org = Organization.objects.nocache().get(pk=org.pk)
        self.assertEqual(org.timezone, FEATURES_ORG.timezone)
        self.assertEqual(org.name, FEATURES_ORG.name)


class ForceRepopulateWithLedgerRowsTest(TestCase):
    def test_force_repopulate_with_ledger_rows(self) -> None:
        for _ in range(2):
            populate_org_delete(force=True)
            populate_org_features_data(force=True)
        self.assertEqual(
            ContributionEntry.objects.nocache()
            .filter(organization_id=ORG_DELETE_ORG.pk)
            .count(),
            2,
        )
        self.assertTrue(
            ContributionEntry.objects.nocache()
            .filter(organization_id=FEATURES_ORG.pk)
            .exists()
        )

    def test_delete_ledger_for_users_lets_a_user_with_points_go(self) -> None:
        populate_org_features_data(force=True)
        player = CustomUser.objects.get(pk=ORG_FEATURES_PLAYERS[0].pk)
        org = Organization.objects.get(pk=FEATURES_ORG.pk)
        award_entry(
            org=org,
            user=player,
            kind=ContributionKind.MANUAL,
            points=4,
            occurred_at=timezone.now(),
        )
        delete_ledger_for_users([player.pk])
        player.delete()
        self.assertFalse(CustomUser.objects.filter(pk=player.pk).exists())


@override_settings(DEBUG=True)
class OrgFeaturesEndpointsTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        populate_org_features_data(force=True)

    def setUp(self) -> None:
        self.factory = APIRequestFactory()

    def _login(self, role: str) -> int:
        request = self.factory.post(f"/api/tests/login-org-features/{role}/")
        request.session = SessionStore()
        return login_org_features(request, role).status_code

    def test_every_role_logs_in(self) -> None:
        for role in ORG_FEATURES_ROLE_USERS:
            self.assertEqual(self._login(role), 200, role)

    def test_unknown_role_is_rejected(self) -> None:
        self.assertEqual(self._login("nobody"), 400)

    def test_data_lists_orgs_users_events_templates(self) -> None:
        body = org_features_data(self.factory.get("/api/tests/org-features/data/")).data
        self.assertEqual(
            {key: value["pk"] for key, value in body["orgs"].items()},
            {
                "features": FEATURES_ORG.pk,
                "locked": LOCKED_FEATURES_ORG.pk,
                "private": PRIVATE_FEATURES_ORG.pk,
            },
        )
        self.assertEqual(set(body["users"]), set(ORG_FEATURES_ROLE_USERS))
        self.assertEqual(set(body["events"]), {"upcoming", "upcoming2", "completed"})
        self.assertEqual(body["events"]["upcoming"]["pk"], _upcoming().pk)
        self.assertEqual(len(body["templates"]), 4)

    def test_reset_returns_fresh_events(self) -> None:
        before = _upcoming().pk
        response = reset_org_features(
            self.factory.post("/api/tests/org-features/reset/")
        )
        self.assertEqual(response.status_code, 200)
        self.assertNotEqual(response.data["events"]["upcoming"]["pk"], before)


@override_settings(DEBUG=True)
class AuthMatrixPromoterTest(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        populate_organizations_and_leagues(force=True)
        populate_test_auth_users(force=True)
        populate_auth_matrix_data(force=True)

    def _org(self) -> Organization:
        return Organization.objects.get(pk=AUTH_MATRIX_ORG.pk)

    def test_promoter_is_wired_into_auth_matrix_org(self) -> None:
        org = self._org()
        self.assertTrue(
            org.promoters.filter(pk=AUTH_MATRIX_ORG_PROMOTER_USER.pk).exists()
        )
        self.assertTrue(
            OrgUser.objects.filter(
                user_id=AUTH_MATRIX_ORG_PROMOTER_USER.pk, organization=org
            ).exists()
        )

    def test_auth_matrix_org_keeps_promotion_locked(self) -> None:
        self.assertFalse(org_has_feature(self._org(), FeatureKey.PROMOTION))

    def test_promoter_login_restores_membership(self) -> None:
        org = self._org()
        org.promoters.clear()
        request = APIRequestFactory().post("/api/tests/login-auth-matrix-org-promoter/")
        request.session = SessionStore()
        self.assertEqual(login_auth_matrix_org_promoter(request).status_code, 200)
        self.assertTrue(
            org.promoters.filter(pk=AUTH_MATRIX_ORG_PROMOTER_USER.pk).exists()
        )
