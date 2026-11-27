from django.urls import URLPattern, path

from org.mmr_requests import internal_views as views

urlpatterns: list[URLPattern] = [
    path(
        "purge-screenshots/",
        views.purge_screenshots,
        name="internal_mmr_purge_screenshots",
    ),
]
