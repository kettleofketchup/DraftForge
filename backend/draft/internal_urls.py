"""Internal hero draft routes (InternalServiceAuth), mounted at the root URLconf."""

from django.urls import URLPattern, path

from draft.views.hero_internal import (
    create_herodraft_for_game,
    list_auto_herodraft_games,
)

urlpatterns: list[URLPattern] = [
    path(
        "api/internal/tournaments/auto-herodraft-games/",
        list_auto_herodraft_games,
    ),
    path(
        "api/internal/games/<int:game_id>/create-herodraft/",
        create_herodraft_for_game,
    ),
]
