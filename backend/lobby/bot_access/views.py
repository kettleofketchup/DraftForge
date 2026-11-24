"""League-scoped bot access API.

`GET api/leagues/<league_id>/bot-access/` and `POST .../refresh/` return a
`BotAccessSnapshot` to league admins. Anyone else, and an unknown league,
gets 404. League admin is self-service, so only site admins get the full bot
roster; other admins see just the bots that already hold the league. Throttles run after the permission check so denied users never
see 429. Upstream failures are 200 with `service.status`.
"""

from __future__ import annotations

import math

from django.contrib.auth.models import AnonymousUser
from django.http import Http404
from django.shortcuts import get_object_or_404
from rest_framework import permissions
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import (
    BaseThrottle,
    SimpleRateThrottle,
    UserRateThrottle,
)
from rest_framework.views import APIView

from app.models import CustomUser
from league.models import League
from league.permissions import has_league_admin_access
from lobby.bot_access.base import BotAccessProvider, empty_snapshot
from lobby.bot_access.registry import get_bot_access, league_game_type
from lobby.bot_access.schemas import BotAccessSnapshot
from telemetry.logging import get_logger

log = get_logger(__name__)

_LOG = {"system": "lobby", "subsystem": "bot_access"}


class BotAccessReadThrottle(UserRateThrottle):
    scope = "bot_access_read"
    rate = "30/min"


class BotAccessRefreshThrottle(UserRateThrottle):
    scope = "bot_access_refresh"
    rate = "6/min"


class BotAccessRefreshGlobalThrottle(SimpleRateThrottle):
    scope = "bot_access_refresh_global"
    rate = "20/min"

    def get_cache_key(self, request: Request, view: APIView) -> str:
        return self.cache_format % {"scope": self.scope, "ident": "all"}


def can_view_full_roster(user: CustomUser | AnonymousUser) -> bool:
    return bool(user.is_staff or user.is_superuser)


def _no_store(response: Response) -> Response:
    response["Cache-Control"] = "no-store"
    return response


def _throttled(
    request: Request, view: APIView, throttles: list[BaseThrottle]
) -> Response | None:
    for throttle in throttles:
        if throttle.allow_request(request, view):
            continue
        log.info(
            "bot_access_throttled",
            scope=getattr(throttle, "scope", None),
            user_id=request.user.pk,
            **_LOG,
        )
        response = Response(
            {"error": "Too many requests. Try again shortly.", "code": "throttled"},
            status=429,
        )
        wait = throttle.wait()
        response["Retry-After"] = str(max(1, math.ceil(wait or 1)))
        return _no_store(response)
    return None


class _BotAccessBase(APIView):
    permission_classes = [permissions.IsAuthenticated]
    access_throttles: tuple[type[BaseThrottle], ...] = ()

    def _load(self, request: Request, league_id: int) -> League:
        league = get_object_or_404(
            League.objects.select_related("organization"), pk=league_id
        )
        if not has_league_admin_access(request.user, league):
            raise Http404
        return league

    def _run(
        self, provider: BotAccessProvider, external_league_id: str, full_roster: bool
    ) -> BotAccessSnapshot:
        raise NotImplementedError

    def _respond(self, request: Request, league_id: int) -> Response:
        league = self._load(request, league_id)
        throttled = _throttled(request, self, [cls() for cls in self.access_throttles])
        if throttled is not None:
            return throttled
        provider = get_bot_access(league_game_type(league))
        if not provider.supported:
            snap = empty_snapshot(provider, None, "unsupported")
        else:
            external_league_id = provider.external_league_id(league)
            if external_league_id is None:
                snap = empty_snapshot(provider, None, "league_not_linked")
            else:
                snap = self._run(
                    provider, external_league_id, can_view_full_roster(request.user)
                )
        return _no_store(Response(snap.model_dump(mode="json")))


class BotAccessView(_BotAccessBase):
    access_throttles = (BotAccessReadThrottle,)

    def _run(
        self, provider: BotAccessProvider, external_league_id: str, full_roster: bool
    ) -> BotAccessSnapshot:
        return provider.snapshot(external_league_id, full_roster=full_roster)

    def get(self, request: Request, league_id: int) -> Response:
        return self._respond(request, league_id)


class BotAccessRefreshView(_BotAccessBase):
    access_throttles = (BotAccessRefreshThrottle, BotAccessRefreshGlobalThrottle)

    def _run(
        self, provider: BotAccessProvider, external_league_id: str, full_roster: bool
    ) -> BotAccessSnapshot:
        return provider.refresh(external_league_id, full_roster=full_roster)

    def post(self, request: Request, league_id: int) -> Response:
        return self._respond(request, league_id)
