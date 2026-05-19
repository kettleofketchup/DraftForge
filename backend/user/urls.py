from django.urls import path

from .views import MeProfileBasePatchView, MeProfileView

urlpatterns = [
    path("me/profile/", MeProfileView.as_view(), name="me-profile"),
    path("me/profile/base/", MeProfileBasePatchView.as_view(), name="me-profile-base"),
]
