from django.urls import include, path
from rest_framework.routers import DefaultRouter

from events.views import (
    EventRepeaterViewSet,
    EventSignupViewSet,
    EventTeamViewSet,
    EventViewSet,
    OrgEventDefaultsViewSet,
)

router = DefaultRouter()
router.register(r"defaults", OrgEventDefaultsViewSet, basename="event-defaults")
router.register(r"repeaters", EventRepeaterViewSet, basename="event-repeater")
router.register(r"signups", EventSignupViewSet, basename="event-signup")
router.register(r"teams", EventTeamViewSet, basename="event-team")
router.register(r"", EventViewSet, basename="event")

urlpatterns = [path("", include(router.urls))]
