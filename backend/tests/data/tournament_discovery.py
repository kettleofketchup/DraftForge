"""Tournament discovery test data for the /tournaments redesign E2E specs.

DISCOVERY_MEMBER belongs to the home org only, so the home org's tournaments
land in "Your organizations" and the away cup in "Other organizations". The
open org's cup has a source event taking user signups, so it also shows under
"My organizations" with a "Signups open" badge.
Dates are absolute: 2099 rows stay upcoming, 2020 rows stay archived.
"""

from datetime import UTC, datetime
from typing import NamedTuple

from tests.data.models import TestLeague, TestOrganization, TestUser


class DiscoveryTournament(NamedTuple):
    pk: int
    name: str
    state: str
    date_played: datetime
    league_pk: int


DISCOVERY_HOME_ORG: TestOrganization = TestOrganization(
    pk=30,
    name="Discovery Home Organization For Very Long Name Overflow Checks",
    description="Isolated organization for tournament discovery E2E tests.",
    timezone="America/New_York",
)

DISCOVERY_AWAY_ORG: TestOrganization = TestOrganization(
    pk=31,
    name="Discovery Away Org",
    description="Second organization for tournament discovery E2E tests.",
    timezone="America/New_York",
)

DISCOVERY_OPEN_ORG: TestOrganization = TestOrganization(
    pk=32,
    name="Discovery Open Org",
    description="Organization whose cup has user signups open.",
    timezone="America/New_York",
)

DISCOVERY_HOME_LEAGUE: TestLeague = TestLeague(
    pk=30,
    name="Discovery Home League With An Exceptionally Long Name",
    steam_league_id=17950,
    organization_names=[DISCOVERY_HOME_ORG.name],
)

DISCOVERY_AWAY_LEAGUE: TestLeague = TestLeague(
    pk=31,
    name="Discovery Away League",
    steam_league_id=17951,
    organization_names=[DISCOVERY_AWAY_ORG.name],
)

DISCOVERY_OPEN_LEAGUE: TestLeague = TestLeague(
    pk=32,
    name="Discovery Open League",
    steam_league_id=17952,
    organization_names=[DISCOVERY_OPEN_ORG.name],
)

DISCOVERY_OPEN_EVENT_NAME = "Discovery Open Signups Event"

DISCOVERY_MEMBER: TestUser = TestUser(
    pk=1100,
    username="discovery_member",
    nickname="Discovery Member",
    discord_id="710000000000001100",
    steam_id_64=76561199110001100,
)

DISCOVERY_TOURNAMENTS: tuple[DiscoveryTournament, ...] = (
    DiscoveryTournament(
        900,
        "Discovery Home Live",
        "in_progress",
        datetime(2099, 1, 1, 18, tzinfo=UTC),
        30,
    ),
    DiscoveryTournament(
        901, "Discovery Home Soon", "future", datetime(2099, 2, 1, 18, tzinfo=UTC), 30
    ),
    DiscoveryTournament(
        902, "Discovery Home Later", "future", datetime(2099, 3, 1, 18, tzinfo=UTC), 30
    ),
    DiscoveryTournament(
        903, "Discovery Home Finished", "past", datetime(2020, 1, 1, 18, tzinfo=UTC), 30
    ),
    DiscoveryTournament(
        904, "Discovery Home Stale", "future", datetime(2020, 2, 1, 18, tzinfo=UTC), 30
    ),
    DiscoveryTournament(
        905, "Discovery Away Cup", "future", datetime(2099, 1, 15, 18, tzinfo=UTC), 31
    ),
    DiscoveryTournament(
        906,
        "Discovery Open Signups Cup",
        "future",
        datetime(2099, 1, 20, 18, tzinfo=UTC),
        32,
    ),
)

DISCOVERY_OPEN_SIGNUPS_TOURNAMENT_PK = 906
