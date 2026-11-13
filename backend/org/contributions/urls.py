from django.urls import path

from org.contributions.views import (
    contributions_entries,
    contributions_entry,
    contributions_leaderboard,
    contributions_member,
    contributions_point_value,
    contributions_point_values,
)

urlpatterns = [
    path(
        "leaderboard/",
        contributions_leaderboard,
        name="org-contributions-leaderboard",
    ),
    path(
        "members/<int:org_user_pk>/",
        contributions_member,
        name="org-contributions-member",
    ),
    path(
        "point-values/",
        contributions_point_values,
        name="org-contributions-point-values",
    ),
    path(
        "point-values/<str:kind>/",
        contributions_point_value,
        name="org-contributions-point-value",
    ),
    path("entries/", contributions_entries, name="org-contributions-entries"),
    path(
        "entries/<int:entry_pk>/",
        contributions_entry,
        name="org-contributions-entry",
    ),
]
