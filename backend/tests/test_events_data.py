"""GET /api/tests/events/data/: the seeded 16-events pks (TEST=true only)."""

from typing import Any

from rest_framework import status
from rest_framework.decorators import (
    api_view,
    authentication_classes,
    permission_classes,
)
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response

from app.models import CustomUser
from common.utils import isTestEnvironment
from events.models import Event
from league.models import League
from org.models import Organization
from tests.data.leagues import EVENTS_LEAGUE, EVENTS_LEAGUE_ALT
from tests.data.organizations import EVENTS_ORG
from tests.data.users import (
    EVENT_ADMIN_USER,
    EVENT_PLAYER_1,
    EVENT_PLAYER_4,
    EVENT_PLAYER_NO_PROFILE,
)

EVENTS_EVENT_NAME = "E2E Signup Event"
USERS = {
    "admin": EVENT_ADMIN_USER,
    "player": EVENT_PLAYER_1,
    "player_4": EVENT_PLAYER_4,
    "no_profile": EVENT_PLAYER_NO_PROFILE,
}


def events_test_data() -> dict[str, Any] | None:
    org = Organization.objects.filter(name=EVENTS_ORG.name).first()
    event = Event.objects.filter(organization=org, name=EVENTS_EVENT_NAME).first()
    # By name: spec 16-events/10 edits steam_league_id.
    leagues = {
        lg.name: lg
        for lg in League.objects.filter(
            organization=org,
            name__in=[EVENTS_LEAGUE.name, EVENTS_LEAGUE_ALT.name],
        )
    }
    users = dict(
        CustomUser.objects.filter(
            username__in=[u.username for u in USERS.values()]
        ).values_list("username", "pk")
    )
    league = leagues.get(EVENTS_LEAGUE.name)
    alt = leagues.get(EVENTS_LEAGUE_ALT.name)
    if org is None or event is None or league is None or alt is None:
        return None
    if len(users) != len(USERS):
        return None
    return {
        "org_pk": org.pk,
        "event_pk": event.pk,
        "events_league_pk": league.pk,
        "alt_league_pk": alt.pk,
        "alt_league_name": alt.name,
        "users": {role: users[u.username] for role, u in USERS.items()},
    }


@api_view(["GET"])
@authentication_classes([])
@permission_classes([AllowAny])
def events_data(request: Request) -> Response:
    if not isTestEnvironment(request):
        return Response({"detail": "Not Found"}, status=status.HTTP_404_NOT_FOUND)
    data = events_test_data()
    if data is None:
        return Response(
            {"detail": "Events test data missing; run just db::populate::all"},
            status=status.HTTP_404_NOT_FOUND,
        )
    return Response(data)
