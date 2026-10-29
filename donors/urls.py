from django.urls import path

from .views import DonorContactView, EligibilityView

urlpatterns = [
    path("me/contact/", DonorContactView.as_view(), name="my-contact"),
    path("<int:donor_id>/contact/", DonorContactView.as_view(), name="donor-contact"),
    path("me/eligibility/", EligibilityView.as_view(), name="my-eligibility"),
    path("<int:donor_id>/eligibility/", EligibilityView.as_view(), name="donor-eligibility"),
]
