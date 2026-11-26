from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCoordinator

from .services import weekly_demand_forecast


class WeeklyForecastView(APIView):
    permission_classes = [IsAuthenticated, IsCoordinator]

    def get(self, request):
        return Response(weekly_demand_forecast())
