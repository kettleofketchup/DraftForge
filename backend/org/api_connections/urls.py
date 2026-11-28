from django.urls import path

from org.api_connections import views

urlpatterns = [
    path("", views.connections, name="org-api-connections"),
    path("<int:connection_id>/", views.connection_detail, name="org-api-connection"),
    path(
        "promotion/",
        views.promotion_stream,
        name="org-api-connections-promotion",
    ),
    path(
        "<int:connection_id>/promotion-binding/",
        views.connection_promotion_binding,
        name="org-api-connection-promotion-binding",
    ),
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
    path(
        "<int:connection_id>/deliveries/",
        views.connection_deliveries,
        name="org-api-connection-deliveries",
    ),
    path(
        "<int:connection_id>/deliveries/resume/",
        views.connection_delivery_recovery,
        {"action": "resume"},
        name="org-api-connection-deliveries-resume",
    ),
    path(
        "<int:connection_id>/deliveries/resync/",
        views.connection_delivery_recovery,
        {"action": "resync"},
        name="org-api-connection-deliveries-resync",
    ),
    path(
        "<int:connection_id>/promotion/outbox/",
        views.connection_promotion_outbox,
        name="org-api-connection-promotion-outbox",
    ),
    path(
        "<int:connection_id>/promotion/resume/",
        views.connection_promotion_recovery,
        {"action": "resume"},
        name="org-api-connection-promotion-resume",
    ),
    path(
        "<int:connection_id>/promotion/send-backlog/",
        views.connection_promotion_recovery,
        {"action": "send-backlog"},
        name="org-api-connection-promotion-send-backlog",
    ),
    path(
        "<int:connection_id>/test/",
        views.connection_test,
        name="org-api-connection-test",
    ),
    path(
        "<int:connection_id>/pull/",
        views.connection_pull,
        name="org-api-connection-pull",
    ),
    path(
        "<int:connection_id>/runs/",
        views.connection_runs,
        name="org-api-connection-runs",
    ),
    path(
        "<int:connection_id>/runs/<uuid:run_id>/",
        views.connection_run_detail,
        name="org-api-connection-run",
    ),
]
