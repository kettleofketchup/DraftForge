from django.urls import path
from rest_framework.parsers import FormParser, MultiPartParser

from org.mmr_requests.throttles import MmrRequestCreateThrottle
from org.mmr_requests.upload_guard import guard_upload
from org.mmr_requests.views import (
    LeagueMmrRequestViewSet,
    MmrRequestViewSet,
    OrgMmrRequestViewSet,
)

MULTIPART = {"parser_classes": [MultiPartParser, FormParser]}

create_view = guard_upload(
    MmrRequestViewSet.as_view(
        {"post": "create"},
        **MULTIPART,
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
    path(
        "<int:pk>/approve/",
        MmrRequestViewSet.as_view({"post": "approve"}),
        name="mmr-request-approve",
    ),
    path(
        "<int:pk>/reject/",
        MmrRequestViewSet.as_view({"post": "reject"}),
        name="mmr-request-reject",
    ),
]

org_urlpatterns = [
    path("", OrgMmrRequestViewSet.as_view({"get": "list"}), name="org-mmr-requests"),
    path(
        "pending-count/",
        OrgMmrRequestViewSet.as_view({"get": "pending_count"}),
        name="org-mmr-requests-pending-count",
    ),
    path(
        "staff-set/",
        guard_upload(OrgMmrRequestViewSet.as_view({"post": "staff_set"}, **MULTIPART)),
        name="org-mmr-requests-staff-set",
    ),
]

league_urlpatterns = [
    path(
        "", LeagueMmrRequestViewSet.as_view({"get": "list"}), name="league-mmr-requests"
    ),
    path(
        "pending-count/",
        LeagueMmrRequestViewSet.as_view({"get": "pending_count"}),
        name="league-mmr-requests-pending-count",
    ),
    path(
        "staff-set/",
        guard_upload(
            LeagueMmrRequestViewSet.as_view({"post": "staff_set"}, **MULTIPART)
        ),
        name="league-mmr-requests-staff-set",
    ),
]
