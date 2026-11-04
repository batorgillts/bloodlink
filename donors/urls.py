from django.urls import path

from .views import (
    DonationCreateView,
    DonationDeleteView,
    DonorContactView,
    DonorRecordDetailView,
    DonorRecordListCreateView,
    EligibilityView,
    WithdrawRegistrationView,
)

urlpatterns = [
    path("", DonorRecordListCreateView.as_view(), name="donor-record-list-create"),
    path("<int:donor_id>/", DonorRecordDetailView.as_view(), name="donor-record-detail"),
    path(
        "<int:donor_id>/donations/<int:donation_id>/",
        DonationDeleteView.as_view(),
        name="delete-donation",
    ),
    path("me/contact/", DonorContactView.as_view(), name="my-contact"),
    path("<int:donor_id>/contact/", DonorContactView.as_view(), name="donor-contact"),
    path("me/eligibility/", EligibilityView.as_view(), name="my-eligibility"),
    path("<int:donor_id>/eligibility/", EligibilityView.as_view(), name="donor-eligibility"),
    path("me/withdraw/", WithdrawRegistrationView.as_view(), name="my-withdraw"),
    path("<int:donor_id>/withdraw/", WithdrawRegistrationView.as_view(), name="donor-withdraw"),
    path("<int:donor_id>/donations/", DonationCreateView.as_view(), name="donor-donations"),
]
