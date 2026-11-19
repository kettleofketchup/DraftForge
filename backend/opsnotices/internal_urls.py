from django.urls import URLPattern, path

from opsnotices import internal_views as views

urlpatterns: list[URLPattern] = [
    path("", views.emit, name="internal_ops_notice_emit"),
    path("resolve/", views.resolve, name="internal_ops_notice_resolve"),
]
