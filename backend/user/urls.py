from django.urls import path

from .views import ping

urlpatterns = [
    path("me/profile/ping/", ping, name="me-profile-ping"),
]
