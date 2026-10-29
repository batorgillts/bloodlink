from django.urls import path

from .views import DonorContactView

urlpatterns = [
    path("me/contact/", DonorContactView.as_view(), name="my-contact"),
    path("<int:donor_id>/contact/", DonorContactView.as_view(), name="donor-contact"),
]
