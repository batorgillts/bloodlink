from django.urls import path

from .views import BloodRequestListCreateView, BloodRequestMatchView

urlpatterns = [
    path(
        "<int:request_id>/matches/",
        BloodRequestMatchView.as_view(),
        name="blood-request-matches",
    ),
    path("", BloodRequestListCreateView.as_view(), name="blood-request-list-create"),
]
