from django.urls import path

from .views import (
    BloodRequestCancelView,
    BloodRequestHistoryView,
    BloodRequestListCreateView,
    BloodRequestMatchView,
    DonorSuggestionsView,
)

urlpatterns = [
    path(
        "<int:request_id>/donor-suggestions/",
        DonorSuggestionsView.as_view(),
        name="blood-request-donor-suggestions",
    ),
    path(
        "<int:request_id>/matches/",
        BloodRequestMatchView.as_view(),
        name="blood-request-matches",
    ),
    path("", BloodRequestListCreateView.as_view(), name="blood-request-list-create"),
    path(
        "<int:request_id>/cancel/",
        BloodRequestCancelView.as_view(),
        name="blood-request-cancel",
    ),
    path(
        "<int:request_id>/history/",
        BloodRequestHistoryView.as_view(),
        name="blood-request-history",
    ),
]
