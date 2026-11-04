from django.urls import path

from .views import BloodRequestListCreateView

urlpatterns = [
    path("", BloodRequestListCreateView.as_view(), name="blood-request-list-create"),
]
