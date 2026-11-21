from django.urls import path

from org.conduct.views import (
    conduct_event_attendance,
    conduct_event_forecast,
    conduct_leaderboard,
    conduct_member,
    conduct_settings,
)

urlpatterns = [
    path("settings/", conduct_settings, name="org-conduct-settings"),
    path("leaderboard/", conduct_leaderboard, name="org-conduct-leaderboard"),
    path("members/<int:org_user_pk>/", conduct_member, name="org-conduct-member"),
    path(
        "events/<int:event_id>/attendance/",
        conduct_event_attendance,
        name="org-conduct-event-attendance",
    ),
    path(
        "events/<int:event_id>/forecast/",
        conduct_event_forecast,
        name="org-conduct-event-forecast",
    ),
]
