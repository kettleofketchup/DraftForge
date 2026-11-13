"""Populate the tournament discovery data (tests.data.tournament_discovery).

Explicit pks: orgs 30/31, leagues 30/31, user 1100, tournaments 900-905.
Used by frontend/tests/playwright/e2e/03-tournaments/04-discovery.spec.ts.
"""

from app.cache_utils import invalidate_obj
from app.models import CustomUser, League, Organization, PositionsModel, Tournament
from tests.data.models import TestLeague, TestOrganization, TestUser
from tests.data.tournament_discovery import (
    DISCOVERY_AWAY_LEAGUE,
    DISCOVERY_AWAY_ORG,
    DISCOVERY_HOME_LEAGUE,
    DISCOVERY_HOME_ORG,
    DISCOVERY_MEMBER,
    DISCOVERY_TOURNAMENTS,
)
from tests.populate.utils import ensure_org_user


def _get_or_create_user(user_data: TestUser, force: bool) -> CustomUser:
    existing = CustomUser.objects.filter(pk=user_data.pk).first()
    if existing and not force:
        return existing
    if existing:
        existing.delete()
    user = CustomUser(
        pk=user_data.pk,
        username=user_data.username,
        nickname=user_data.nickname,
        discordId=user_data.discord_id,
        steamid=user_data.get_steam_id_64(),
        positions=PositionsModel.objects.create(),
    )
    user.set_unusable_password()
    user.save()
    return user


def _upsert_org(data: TestOrganization) -> Organization:
    org, _ = Organization.objects.update_or_create(
        pk=data.pk,
        defaults={
            "name": data.name,
            "description": data.description,
            "logo": data.logo,
            "timezone": data.timezone,
        },
    )
    return org


def _upsert_league(data: TestLeague, org: Organization) -> League:
    league, _ = League.objects.update_or_create(
        pk=data.pk,
        defaults={
            "name": data.name,
            "steam_league_id": data.steam_league_id,
            "organization": org,
            "timezone": data.timezone,
        },
    )
    return league


def populate_tournament_discovery(force: bool = False) -> None:
    print("Populating tournament discovery test data...")

    home_org = _upsert_org(DISCOVERY_HOME_ORG)
    away_org = _upsert_org(DISCOVERY_AWAY_ORG)
    leagues = {
        DISCOVERY_HOME_LEAGUE.pk: _upsert_league(DISCOVERY_HOME_LEAGUE, home_org),
        DISCOVERY_AWAY_LEAGUE.pk: _upsert_league(DISCOVERY_AWAY_LEAGUE, away_org),
    }

    for row in DISCOVERY_TOURNAMENTS:
        Tournament.objects.update_or_create(
            pk=row.pk,
            defaults={
                "name": row.name,
                "state": row.state,
                "date_played": row.date_played,
                "league": leagues[row.league_pk],
            },
        )

    member = _get_or_create_user(DISCOVERY_MEMBER, force)
    ensure_org_user(member, home_org)

    for obj in (home_org, away_org, *leagues.values(), member):
        invalidate_obj(obj)

    print(
        f"Tournament discovery data ready: orgs {home_org.pk}/{away_org.pk}, "
        f"{len(DISCOVERY_TOURNAMENTS)} tournaments"
    )
