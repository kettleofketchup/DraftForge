from django.urls import path

from org.conduct.views import conduct_leaderboard, conduct_member, conduct_settings

urlpatterns = [
    path("settings/", conduct_settings, name="org-conduct-settings"),
    path("leaderboard/", conduct_leaderboard, name="org-conduct-leaderboard"),
    path("members/<int:org_user_pk>/", conduct_member, name="org-conduct-member"),
]
