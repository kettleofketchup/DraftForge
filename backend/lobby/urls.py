"""User-facing lobby API, mounted under `api/games/<int:game_pk>/lobby/`."""

from django.urls import URLPattern, path

from lobby import views

urlpatterns: list[URLPattern] = [
    path("", views.GameLobbyView.as_view(), name="game_lobby"),
    path("invite/", views.GameLobbyInviteView.as_view(), name="game_lobby_invite"),
    path("launch/", views.GameLobbyLaunchView.as_view(), name="game_lobby_launch"),
]
