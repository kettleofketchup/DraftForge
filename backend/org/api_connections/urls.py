from django.urls import path

from org.api_connections import views

urlpatterns = [
    path("", views.connections, name="org-api-connections"),
    path("<int:connection_id>/", views.connection_detail, name="org-api-connection"),
    path(
        "<int:connection_id>/issue-key/",
        views.connection_key,
        {"action": "issue"},
        name="org-api-connection-issue",
    ),
    path(
        "<int:connection_id>/rotate-key/",
        views.connection_key,
        {"action": "rotate"},
        name="org-api-connection-rotate",
    ),
    path(
        "<int:connection_id>/revoke-key/",
        views.connection_key,
        {"action": "revoke"},
        name="org-api-connection-revoke",
    ),
]
