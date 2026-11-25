from __future__ import annotations

from typing import Any

from cacheops import cached_as
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponseRedirect
from django.shortcuts import redirect
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import (
    AllowAny,
)
from rest_framework.request import Request
from rest_framework.response import Response
from social_django.utils import load_strategy

from league.models import League
from org.models import Organization
from telemetry.logging import get_logger
from tournament.models import Game, Tournament

from .decorators import render_to

log = get_logger(__name__)


def logout(request: HttpRequest) -> HttpResponseRedirect:
    auth_logout(request)
    return redirect("/")


@render_to("home.html")
def home(request: HttpRequest) -> HttpResponseRedirect | None:
    """Home view, displays login mechanism"""
    if request.user.is_authenticated:
        return redirect("done")
    return None


@login_required
@render_to("home.html")
def done(request: HttpRequest) -> None:
    """Login complete view, displays user data"""
    return


@render_to("home.html")
def validation_sent(request: HttpRequest) -> dict[str, Any]:
    return {
        "validation_sent": True,
        "email": request.session.get("email_validation_address"),
    }


@render_to("home.html")
def require_email(request: HttpRequest) -> dict[str, Any]:
    strategy = load_strategy()
    partial_token = request.GET.get("partial_token")
    partial = strategy.partial_load(partial_token)
    return {
        "email_required": True,
        "partial_backend_name": partial.backend,
        "partial_token": partial_token,
    }


@render_to("home.html")
def require_country(request: HttpRequest) -> dict[str, Any]:
    strategy = load_strategy()
    partial_token = request.GET.get("partial_token")
    partial = strategy.partial_load(partial_token)
    return {
        "country_required": True,
        "partial_backend_name": partial.backend,
        "partial_token": partial_token,
    }


@render_to("home.html")
def require_city(request: HttpRequest) -> dict[str, Any]:
    strategy = load_strategy()
    partial_token = request.GET.get("partial_token")
    partial = strategy.partial_load(partial_token)
    return {
        "city_required": True,
        "partial_backend_name": partial.backend,
        "partial_token": partial_token,
    }


@api_view(["GET"])
@permission_classes([AllowAny])
def home_stats(request: Request) -> Response:
    """
    Cached endpoint for home page statistics.
    Returns counts only, much more efficient than fetching full objects.
    """
    cache_key = "home_stats"

    @cached_as(
        Tournament,
        Game,
        Organization,
        League,
        extra=cache_key,
        timeout=60 * 5,
    )
    def get_stats() -> dict[str, int]:
        return {
            "tournament_count": Tournament.objects.count(),
            "game_count": Game.objects.count(),
            "organization_count": Organization.objects.count(),
            "league_count": League.objects.count(),
        }

    return Response(get_stats())
