from django.urls import path

from org.conduct.views import conduct_settings

urlpatterns = [
    path("settings/", conduct_settings, name="org-conduct-settings"),
]
