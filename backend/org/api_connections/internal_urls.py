from django.urls import URLPattern, path

from org.api_connections import internal_views as views

urlpatterns: list[URLPattern] = [
    path("claim/", views.claim, name="internal_org_api_sync_claim"),
    path("runs/<uuid:run_id>/step/", views.run_step, name="internal_org_api_sync_run"),
    path(
        "deliveries/<uuid:delivery_id>/step/",
        views.delivery_step,
        name="internal_org_api_sync_delivery",
    ),
    path(
        "promotion/step/",
        views.promotion_step,
        name="internal_org_api_sync_promotion",
    ),
    path("cleanup/", views.cleanup, name="internal_org_api_sync_cleanup"),
]
