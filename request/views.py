from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCoordinator

from . import services
from .serializers import (
    BloodRequestSerializer,
    ConfirmCancelSerializer,
    RequestEventSerializer,
)


class BloodRequestListCreateView(APIView):
    """US-11: coordinators can log requests and list all request records."""

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


class BloodRequestCancelView(APIView):
    """US-19: confirm cancellation, release reserved units, and log the change."""

    permission_classes = [IsAuthenticated, IsCoordinator]

    def post(self, request, request_id):
        confirmation = ConfirmCancelSerializer(data=request.data)
        confirmation.is_valid(raise_exception=True)
        blood_request, released_units = services.cancel_blood_request(
            request_id,
            request.user,
        )
        return Response(
            {
                **BloodRequestSerializer(blood_request).data,
                "released_units": released_units,
            }
        )


class BloodRequestHistoryView(APIView):
    """Coordinator-only append-only history for one blood request."""

    permission_classes = [IsAuthenticated, IsCoordinator]

    def get(self, request, request_id):
        events = services.get_request_history(request_id)
        return Response(RequestEventSerializer(events, many=True).data)
