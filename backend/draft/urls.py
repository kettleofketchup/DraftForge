"""Public hero and team draft HTTP routes, mounted at the root URLconf with full paths."""

from django.urls import URLPattern, path

from draft.views.hero import (
    abandon_draft,
    create_herodraft,
    do_submit_choice,
    do_submit_pick,
    do_trigger_roll,
    get_herodraft,
    list_available_heroes,
    list_events,
    pause_draft,
    reset_draft,
    resume_draft,
    set_ready,
)
from draft.views.hero_ssr import HeroDraftSSRView
from draft.views.team import (
    teamdraft_pause,
    teamdraft_resume,
    teamdraft_set_ready,
    teamdraft_start,
)
from draft.views.team_api import DraftCreateView, DraftRoundCreateView
from draft.views.team_picks import pick_player_for_round, undo_last_pick
from draft.views.team_setup import (
    generate_draft_rounds,
    get_draft_style_mmrs,
    rebuild_team,
)

urlpatterns: list[URLPattern] = [
    path(
        "api/games/<int:game_pk>/create-herodraft/",
        create_herodraft,
        name="create_herodraft",
    ),
    path("api/herodraft/<int:draft_pk>/", get_herodraft, name="get_herodraft"),
    path(
        "api/herodraft/<int:draft_pk>/set-ready/", set_ready, name="herodraft_set_ready"
    ),
    path(
        "api/herodraft/<int:draft_pk>/trigger-roll/",
        do_trigger_roll,
        name="herodraft_trigger_roll",
    ),
    path(
        "api/herodraft/<int:draft_pk>/submit-choice/",
        do_submit_choice,
        name="herodraft_submit_choice",
    ),
    path(
        "api/herodraft/<int:draft_pk>/submit-pick/",
        do_submit_pick,
        name="herodraft_submit_pick",
    ),
    path(
        "api/herodraft/<int:draft_pk>/list-events/",
        list_events,
        name="herodraft_list_events",
    ),
    path(
        "api/herodraft/<int:draft_pk>/list-available-heroes/",
        list_available_heroes,
        name="herodraft_list_available_heroes",
    ),
    path(
        "api/herodraft/<int:draft_pk>/abandon/",
        abandon_draft,
        name="herodraft_abandon",
    ),
    path(
        "api/herodraft/<int:draft_pk>/reset/",
        reset_draft,
        name="herodraft_reset",
    ),
    path(
        "api/herodraft/<int:draft_pk>/pause/",
        pause_draft,
        name="herodraft_pause",
    ),
    path(
        "api/herodraft/<int:draft_pk>/resume/",
        resume_draft,
        name="herodraft_resume",
    ),
    path(
        "api/herodraft/<int:pk>/ssr/", HeroDraftSSRView.as_view(), name="herodraft_ssr"
    ),
    path("api/draft/get-style-mmrs", get_draft_style_mmrs, name="get-draft-style-mmrs"),
    path("api/draft/register", DraftCreateView.as_view()),
    path("api/draftround/register", DraftRoundCreateView.as_view()),
    path("api/tournaments/init-draft", generate_draft_rounds, name="init-draft"),
    path("api/tournaments/draft-rebuild", rebuild_team, name="draft-rebuild"),
    path("api/tournaments/pick_player", pick_player_for_round, name="pick_player"),
    path("api/tournaments/undo-pick", undo_last_pick, name="undo-pick"),
    path(
        "api/draft/<int:draft_pk>/ready/", teamdraft_set_ready, name="teamdraft_ready"
    ),
    path("api/draft/<int:draft_pk>/start/", teamdraft_start, name="teamdraft_start"),
    path("api/draft/<int:draft_pk>/pause/", teamdraft_pause, name="teamdraft_pause"),
    path("api/draft/<int:draft_pk>/resume/", teamdraft_resume, name="teamdraft_resume"),
]
