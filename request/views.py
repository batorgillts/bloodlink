from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCoordinator

from . import donor_suggestions, matching, services
from .serializers import (
    BloodRequestSerializer,
    ConfirmCancelSerializer,
    MatchedUnitSerializer,
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


class DonorSuggestionsView(APIView):
    """compatible donors who are eligible today, to contact when stock is short."""

    permission_classes = [IsAuthenticated, IsCoordinator]

    def get(self, request, request_id):
        blood_request, donation_type, suggestions = donor_suggestions.suggest_donors(request_id)
        donors = [
            {
                "donor_id": donor.pk,
                "full_name": donor.full_name,
                "blood_type": donor.blood_type,
                "is_identical": donor.is_identical,
                "last_donation_date": donor.last_donation_date,
                "next_eligible_date": row["next_eligible_date"],
                "email": donor.user.email,
                "phone": donor.phone,
            }
            for donor, row in suggestions
        ]
        return Response(
            {
                "request_id": blood_request.pk,
                "blood_type": blood_request.blood_type,
                "component": blood_request.component,
                "donation_type": donation_type,
                "donors": donors,
                "message": "" if donors else donor_suggestions.NO_DONORS_MESSAGE,
            }
        )
