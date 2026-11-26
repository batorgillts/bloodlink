from django.urls import path

from .views import WeeklyForecastView

urlpatterns = [path("weekly/", WeeklyForecastView.as_view(), name="weekly-forecast")]
