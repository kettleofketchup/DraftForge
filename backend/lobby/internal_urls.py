"""Internal lobby API, mounted under `api/internal/lobbies/` (X-Internal-Token).

`events/` is the dota_lobby webhook receiver; the rest serve lobby.tasks.
"""

from django.urls import URLPattern, path

from lobby import views_internal as views

urlpatterns: list[URLPattern] = [
    path("events/", views.webhook_events, name="internal_lobby_webhook_events"),
    path("eligible-games/", views.eligible_games, name="internal_lobby_eligible_games"),
    path("active/", views.active, name="internal_lobby_active"),
    path("close-pending/", views.close_pending, name="internal_lobby_close_pending"),
    path("games/<int:game_id>/claim/", views.claim, name="internal_lobby_claim"),
    path("<int:pk>/", views.detail, name="internal_lobby_detail"),
    path("<int:pk>/accepted/", views.accepted, name="internal_lobby_accepted"),
    path("<int:pk>/rejected/", views.rejected, name="internal_lobby_rejected"),
    path("<int:pk>/conflict/", views.conflict, name="internal_lobby_conflict"),
    path("<int:pk>/sync/", views.sync, name="internal_lobby_sync"),
    path("<int:pk>/close-done/", views.close_done, name="internal_lobby_close_done"),
    path("<int:pk>/notify/", views.notify_info, name="internal_lobby_notify"),
]
