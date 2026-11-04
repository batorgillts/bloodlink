from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCoordinator

from . import services
from .serializers import BloodRequestSerializer


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
