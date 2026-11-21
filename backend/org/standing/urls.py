from django.urls import path

from org.standing.views import standing_leaderboard, standing_tracks

urlpatterns = [
    path("tracks/", standing_tracks, name="org-standing-tracks"),
    path(
        "<str:track>/leaderboard/",
        standing_leaderboard,
        name="org-standing-leaderboard",
    ),
]
