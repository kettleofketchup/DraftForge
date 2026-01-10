from django.urls import path

from app.views.bracket import (
    advance_winner,
    generate_bracket,
    get_bracket,
    save_bracket,
    set_team_placement,
)

from .functions.generate import gen_double_elim

urlpatterns = [
    path("gen_double_elim/", gen_double_elim, name="gen_double_elim"),
    # Bracket API endpoints
    path("tournaments/<int:tournament_id>/", get_bracket, name="get_bracket"),
    path(
        "tournaments/<int:tournament_id>/generate/",
        generate_bracket,
        name="generate_bracket",
    ),
    path("tournaments/<int:tournament_id>/save/", save_bracket, name="save_bracket"),
    path(
        "tournaments/<int:tournament_id>/teams/<int:team_id>/placement/",
        set_team_placement,
        name="set_team_placement",
    ),
    path("games/<int:game_id>/advance-winner/", advance_winner, name="advance_winner"),
]
