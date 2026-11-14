from django.urls import path

from org.promotion.views import (
    promotion_candidates,
    promotion_events,
    promotion_placeholders,
    promotion_render,
    promotion_send,
    promotion_sends,
    promotion_template,
    promotion_templates,
)

urlpatterns = [
    path(
        "placeholders/",
        promotion_placeholders,
        name="org-promotion-placeholders",
    ),
    path("templates/", promotion_templates, name="org-promotion-templates"),
    path(
        "templates/<int:template_pk>/",
        promotion_template,
        name="org-promotion-template",
    ),
    path("events/", promotion_events, name="org-promotion-events"),
    path(
        "events/<int:event_id>/candidates/",
        promotion_candidates,
        name="org-promotion-candidates",
    ),
    path(
        "events/<int:event_id>/render/",
        promotion_render,
        name="org-promotion-render",
    ),
    path(
        "events/<int:event_id>/sends/",
        promotion_sends,
        name="org-promotion-sends",
    ),
    path("sends/<int:send_pk>/", promotion_send, name="org-promotion-send"),
]
