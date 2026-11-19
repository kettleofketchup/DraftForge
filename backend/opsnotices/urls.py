from django.urls import URLPattern, path

from opsnotices import views

urlpatterns: list[URLPattern] = [
    path(
        "api/organizations/<int:org_id>/ops-notices/",
        views.org_ops_notices,
        name="org_ops_notices",
    ),
    path(
        "api/events/<int:event_id>/ops-notices/",
        views.event_ops_notices,
        name="event_ops_notices",
    ),
    path(
        "api/organizations/<int:org_id>/ops-notices/<int:notice_id>/resolve/",
        views.org_ops_notice_resolve,
        name="org_ops_notice_resolve",
    ),
    path(
        "api/events/<int:event_id>/ops-notices/<int:notice_id>/resolve/",
        views.event_ops_notice_resolve,
        name="event_ops_notice_resolve",
    ),
]
