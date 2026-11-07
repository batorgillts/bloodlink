from django.urls import path

from .views import (
    BloodRequestCancelView,
    BloodRequestHistoryView,
    BloodRequestListCreateView,
)

urlpatterns = [
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
