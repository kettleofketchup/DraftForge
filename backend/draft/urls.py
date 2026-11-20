"""Public hero draft HTTP routes, mounted at the root URLconf with full paths."""

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
]
