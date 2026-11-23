from django.urls import path

from org.leadership.views import (
    leadership_event_release,
    leadership_event_reviews,
    leadership_member,
    leadership_mine,
    leadership_pending,
    leadership_review,
    leadership_review_unvoid,
    leadership_review_void,
    leadership_settings,
    leadership_trait,
    leadership_traits,
)

urlpatterns = [
    path("settings/", leadership_settings, name="org-leadership-settings"),
    path("traits/", leadership_traits, name="org-leadership-traits"),
    path("traits/<slug:key>/", leadership_trait, name="org-leadership-trait"),
    path("reviews/pending/", leadership_pending, name="org-leadership-pending"),
    path("reviews/mine/", leadership_mine, name="org-leadership-mine"),
    path(
        "reviews/<int:review_pk>/void/",
        leadership_review_void,
        name="org-leadership-review-void",
    ),
    path(
        "reviews/<int:review_pk>/unvoid/",
        leadership_review_unvoid,
        name="org-leadership-review-unvoid",
    ),
    path(
        "events/<int:event_id>/captains/<int:org_user_id>/review/",
        leadership_review,
        name="org-leadership-review",
    ),
    path(
        "events/<int:event_id>/reviews/",
        leadership_event_reviews,
        name="org-leadership-event-reviews",
    ),
    path(
        "events/<int:event_id>/release/",
        leadership_event_release,
        name="org-leadership-event-release",
    ),
    path("members/<int:org_user_id>/", leadership_member, name="org-leadership-member"),
]
