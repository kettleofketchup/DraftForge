from django.urls import URLPattern, path

from org.leadership import internal_views

urlpatterns: list[URLPattern] = [
    path(
        "review-dms/plan/",
        internal_views.review_dms_plan,
        name="internal_leadership_review_dms_plan",
    ),
]
