from django.urls import path

from .views import (
    MeProfileBasePatchView,
    MeProfileGamePatchView,
    MeProfileView,
)

urlpatterns = [
    path("me/profile/", MeProfileView.as_view(), name="me-profile"),
    path("me/profile/base/", MeProfileBasePatchView.as_view(), name="me-profile-base"),
    path(
        "me/profile/game/<str:game>/",
        MeProfileGamePatchView.as_view(),
        name="me-profile-game",
    ),
]
