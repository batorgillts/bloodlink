from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCoordinator

from . import matching, services
from .serializers import BloodRequestSerializer, MatchedUnitSerializer


class BloodRequestListCreateView(APIView):
    """US-11: coordinators can log requests and list/filter the request records."""

    permission_classes = [IsAuthenticated, IsCoordinator]

    def get(self, request):
        records = services.list_blood_requests()
        return Response(BloodRequestSerializer(records, many=True).data)

    def post(self, request):
        data = BloodRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        record = services.log_blood_request(data.validated_data, request.user)
        return Response(
            BloodRequestSerializer(record).data,
            status=status.HTTP_201_CREATED,
        )


class BloodRequestMatchView(APIView):
    """Suggest compatible units without reserving or changing inventory."""

    permission_classes = [IsAuthenticated, IsCoordinator]

    def get(self, request, request_id):
        units = MatchedUnitSerializer(matching.match_blood_request(request_id), many=True).data
        return Response(
            {
                "request_id": request_id,
                "units": units,
                "message": "" if units else "No compatible units available",
            }
        )
