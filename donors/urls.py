from django.urls import path

from .views import (
    DonationCreateView,
    DonorContactView,
    DonorRecordDetailView,
    DonorRecordListCreateView,
    EligibilityView,
)

urlpatterns = [
    path("", DonorRecordListCreateView.as_view(), name="donor-record-list-create"),
    path("<int:donor_id>/", DonorRecordDetailView.as_view(), name="donor-record-detail"),
    path("me/contact/", DonorContactView.as_view(), name="my-contact"),
    path("<int:donor_id>/contact/", DonorContactView.as_view(), name="donor-contact"),
    path("me/eligibility/", EligibilityView.as_view(), name="my-eligibility"),
    path("<int:donor_id>/eligibility/", EligibilityView.as_view(), name="donor-eligibility"),
    path("<int:donor_id>/", DonorRecordDetailView.as_view(), name="donor-record-detail"),
    path("<int:donor_id>/donations/", DonationCreateView.as_view(), name="donor-donations"),
]
