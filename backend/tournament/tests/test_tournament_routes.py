from typing import Any

from channels.routing import URLRouter
from django.contrib import admin
from django.test import SimpleTestCase, TestCase
from django.urls import ResolverMatch, resolve
from rest_framework.test import APIClient

from backend import asgi
from tournament.models import TeamLog

TOURNAMENT_HTTP_ROUTES: tuple[tuple[str, str, str | None, str], ...] = (
    (
        "/api/tournaments/",
        "tournament.views.tournament",
        "tournaments-list",
        "TournamentView",
    ),
    (
        "/api/tournaments/1/",
        "tournament.views.tournament",
        "tournaments-detail",
        "TournamentView",
    ),
    (
        "/api/tournaments/1/discord-logs/",
        "tournament.views.tournament",
        "tournaments-discord-logs",
        "TournamentView",
    ),
    (
        "/api/tournaments/1/viewer/",
        "tournament.views.tournament",
        "tournaments-viewer",
        "TournamentView",
    ),
    ("/api/teams/", "tournament.views.team", "teams-list", "TeamView"),
    ("/api/teams/1/", "tournament.views.team", "teams-detail", "TeamView"),
    ("/api/teams/1/dropout/", "tournament.views.team", "teams-dropout", "TeamView"),
    ("/api/teams/1/history/", "tournament.views.team", "teams-history", "TeamView"),
    ("/api/teams/1/rename/", "tournament.views.team", "teams-rename", "TeamView"),
    ("/api/teams/1/restore/", "tournament.views.team", "teams-restore", "TeamView"),
    (
        "/api/teams/1/set-captain/",
        "tournament.views.team",
        "teams-set-captain",
        "TeamView",
    ),
    (
        "/api/teams/1/set-deputy/",
        "tournament.views.team",
        "teams-set-deputy",
        "TeamView",
    ),
    ("/api/teams/1/standins/", "tournament.views.team", "teams-standins", "TeamView"),
    (
        "/api/teams/1/standins/remove/",
        "tournament.views.team",
        "teams-standins-remove",
        "TeamView",
    ),
    ("/api/teams/1/sub-in/", "tournament.views.team", "teams-sub-in", "TeamView"),
    ("/api/teams/1/usage/", "tournament.views.team", "teams-usage", "TeamView"),
    ("/api/games/", "tournament.views.game", "games-list", "GameView"),
    ("/api/games/1/", "tournament.views.game", "games-detail", "GameView"),
    (
        "/api/tournaments-basic/",
        "tournament.views.tournament",
        "tournaments-basic-list",
        "TournamentsBasicView",
    ),
    (
        "/api/tournaments-basic/1/",
        "tournament.views.tournament",
        "tournaments-basic-detail",
        "TournamentsBasicView",
    ),
    (
        "/api/tournaments-list/",
        "tournament.views.tournament",
        "tournaments-list-list",
        "TournamentListView",
    ),
    (
        "/api/tournaments-list/1/",
        "tournament.views.tournament",
        "tournaments-list-detail",
        "TournamentListView",
    ),
    (
        "/api/tournament/register",
        "tournament.views.tournament",
        None,
        "TournamentCreateView",
    ),
    ("/api/team/register", "tournament.views.team", None, "TeamCreateView"),
    ("/api/game/register", "tournament.views.game", None, "GameCreateView"),
    (
        "/api/organizations/1/import-csv/",
        "tournament.views.csv_import",
        "import_csv_org",
        "import_csv_org",
    ),
    (
        "/api/tournaments/1/import-csv/",
        "tournament.views.csv_import",
        "import_csv_tournament",
        "import_csv_tournament",
    ),
    (
        "/api/bracket/tournaments/1/",
        "tournament.views.bracket",
        "get_bracket",
        "get_bracket",
    ),
    (
        "/api/bracket/tournaments/1/generate/",
        "tournament.views.bracket",
        "generate_bracket",
        "generate_bracket",
    ),
    (
        "/api/bracket/tournaments/1/save/",
        "tournament.views.bracket",
        "save_bracket",
        "save_bracket",
    ),
    (
        "/api/bracket/tournaments/1/teams/2/placement/",
        "tournament.views.bracket",
        "set_team_placement",
        "set_team_placement",
    ),
    (
        "/api/bracket/games/1/advance-winner/",
        "tournament.views.bracket",
        "advance_winner",
        "advance_winner",
    ),
    (
        "/api/tournaments/1/members/",
        "tournament.views.members",
        "add_tournament_member",
        "add_tournament_member",
    ),
    (
        "/api/tournaments/1/ssr/",
        "tournament.ssr",
        "tournament_ssr",
        "TournamentSSRView",
    ),
    (
        "/api/internal/tournaments/1/full/",
        "tournament.views.internal",
        None,
        "get_tournament_for_task",
    ),
    (
        "/api/internal/tournaments/1/participants/",
        "tournament.views.internal",
        None,
        "get_tournament_participants",
    ),
    (
        "/api/internal/games/1/participants/",
        "tournament.views.internal",
        None,
        "get_match_participants",
    ),
)

WS_ROUTES: tuple[tuple[str, str, str, str | None], ...] = (
    (
        "api/tournament/<int:tournament_id>/",
        "tournament.consumers",
        "TournamentConsumer",
        None,
    ),
    (
        "api/discord/activity/draft/<int:draft_id>/",
        "draft.consumers.hero",
        "HeroDraftConsumer",
        "hero",
    ),
    (
        "api/herodraft/<int:draft_id>/",
        "draft.consumers.hero",
        "HeroDraftConsumer",
        None,
    ),
    (
        "api/discord/activity/team-draft/<int:draft_id>/",
        "draft.consumers.team",
        "DraftConsumer",
        "team",
    ),
    ("api/draft/<int:draft_id>/", "draft.consumers.team", "DraftConsumer", None),
)

EXPECTED_API_ROOT_KEYS: frozenset[str] = frozenset(
    {
        "claim-requests",
        "draftrounds",
        "drafts",
        "games",
        "leagues",
        "organizations",
        "teams",
        "tournaments",
        "tournaments-basic",
        "tournaments-list",
        "users",
    }
)


def _view_target(match: ResolverMatch) -> tuple[str, str]:
    view = getattr(match.func, "cls", None) or getattr(match.func, "view_class", None)
    if view is not None:
        return view.__module__, view.__name__
    return match.func.__module__, match.func.__name__


class TournamentRouteResolutionTests(SimpleTestCase):
    def test_create_team_from_captain_route(self) -> None:
        match = resolve("/api/tournaments/create-team-from-captain")
        self.assertEqual(match.func.__module__, "tournament.functions")
        self.assertEqual(match.func.cls.__module__, "tournament.functions")
        self.assertEqual(match.url_name, "create-team-from-captain")

    def test_http_routes_resolve_to_tournament_views(self) -> None:
        for path, module, url_name, view in TOURNAMENT_HTTP_ROUTES:
            with self.subTest(path=path):
                match = resolve(path)
                self.assertEqual(_view_target(match), (module, view))
                self.assertEqual(match.url_name, url_name)


def _websocket_router() -> URLRouter:
    app: Any = asgi.application.application_mapping["websocket"]
    while not isinstance(app, URLRouter):
        app = getattr(app, "inner", None) or app.application
    return app


def _ws_target(callback: Any) -> tuple[str, str, str | None]:
    kind = getattr(callback, "kind", None)
    consumer = (callback.app if kind else callback).consumer_class
    return consumer.__module__, consumer.__name__, kind


class TournamentWebSocketRouteTests(SimpleTestCase):
    def test_ws_route_resolves_to_tournament_consumer(self) -> None:
        routes = [
            (str(route.pattern), *_ws_target(route.callback))
            for route in _websocket_router().routes
        ]
        self.assertEqual(routes, list(WS_ROUTES))


class TournamentAdminTests(SimpleTestCase):
    def test_admin_registers_teamlog(self) -> None:
        self.assertEqual(
            admin.site._registry[TeamLog].__class__.__module__, "tournament.admin"
        )


class ApiRootTests(TestCase):
    def test_api_root_lists_same_prefixes(self) -> None:
        response = APIClient().get("/api/", HTTP_ACCEPT="application/json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(frozenset(response.json()), EXPECTED_API_ROOT_KEYS)
