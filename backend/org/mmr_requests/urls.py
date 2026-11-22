from django.urls import path
from rest_framework.parsers import FormParser, MultiPartParser

from org.mmr_requests.throttles import MmrRequestCreateThrottle
from org.mmr_requests.upload_guard import guard_upload
from org.mmr_requests.views import MmrRequestViewSet

create_view = guard_upload(
    MmrRequestViewSet.as_view(
        {"post": "create"},
        parser_classes=[MultiPartParser, FormParser],
        throttle_classes=[MmrRequestCreateThrottle],
    )
)

urlpatterns = [
    path("", create_view, name="mmr-request-create"),
    path("mine/", MmrRequestViewSet.as_view({"get": "mine"}), name="mmr-request-mine"),
    path(
        "<int:pk>/cancel/",
        MmrRequestViewSet.as_view({"post": "cancel"}),
        name="mmr-request-cancel",
    ),
    path(
        "<int:pk>/screenshot/",
        MmrRequestViewSet.as_view({"get": "screenshot"}),
        name="mmr-request-screenshot",
    ),
]
