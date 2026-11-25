from django.urls import path

from org.integration.views import (
    ContactReceiptsView,
    ContributionTotalsView,
    EventRecipientsView,
)

urlpatterns = [
    path(
        "v1/events/<int:event_id>/recipients/",
        EventRecipientsView.as_view(),
        name="org-integration-event-recipients",
    ),
    path(
        "v1/contact-receipts/",
        ContactReceiptsView.as_view(),
        name="org-integration-contact-receipts",
    ),
    path(
        "v1/contributions/",
        ContributionTotalsView.as_view(),
        name="org-integration-contributions",
    ),
]
