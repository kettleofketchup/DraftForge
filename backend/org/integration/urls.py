from django.urls import path

from org.integration.views import EventRecipientsView

urlpatterns = [
    path(
        "v1/events/<int:event_id>/recipients/",
        EventRecipientsView.as_view(),
        name="org-integration-event-recipients",
    ),
]
