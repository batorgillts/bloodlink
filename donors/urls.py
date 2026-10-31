from django.urls import path

from .views import DonationDeleteView, DonorContactView, DonorDeleteView, EligibilityView

urlpatterns = [
    path("<int:donor_id>/", DonorDeleteView.as_view(), name="delete-donor"),
    path(
        "<int:donor_id>/donations/<int:donation_id>/",
        DonationDeleteView.as_view(),
        name="delete-donation",
    ),
    path("me/contact/", DonorContactView.as_view(), name="my-contact"),
    path("<int:donor_id>/contact/", DonorContactView.as_view(), name="donor-contact"),
    path("me/eligibility/", EligibilityView.as_view(), name="my-eligibility"),
    path("<int:donor_id>/eligibility/", EligibilityView.as_view(), name="donor-eligibility"),
]
