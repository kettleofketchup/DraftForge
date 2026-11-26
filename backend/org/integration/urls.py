from django.urls import path

from org.integration.views import ContactReceiptsView

urlpatterns = [
    path(
        "v1/contact-receipts/",
        ContactReceiptsView.as_view(),
        name="org-integration-contact-receipts",
    ),
]
