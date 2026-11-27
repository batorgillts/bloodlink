from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCoordinator

from . import donor_suggestions, matching, services
from .serializers import (
    BloodRequestListParamsSerializer,
    BloodRequestSerializer,
    ConfirmCancelSerializer,
    MatchedUnitSerializer,
    RequestAuditSerializer,
    RequestEventSerializer,
    RequestHistoryQuerySerializer,
    ReserveUnitsSerializer,
)


def reject_history_change():
    """US-20: a stored history entry cannot be edited or deleted."""
    return Response(
        {"detail": "Request history cannot be edited or deleted."},
        status=status.HTTP_405_METHOD_NOT_ALLOWED,
    )


class BloodRequestListCreateView(APIView):
    """US-11: coordinators can log requests and list all request records."""

    permission_classes = [IsAuthenticated, IsCoordinator]

    def get(self, request):
        params = BloodRequestListParamsSerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        records = services.list_blood_requests(status=params.validated_data.get("status"))
        return Response(BloodRequestSerializer(records, many=True).data)

    def post(self, request):
        data = BloodRequestSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        record = services.log_blood_request(data.validated_data, request.user)
        return Response(
            BloodRequestSerializer(record).data,
            status=status.HTTP_201_CREATED,
        )


class BloodRequestDetailView(APIView):
    """US-16: open one request and see the units reserved for it."""

    permission_classes = [IsAuthenticated, IsCoordinator]

    def get(self, request, request_id):
        blood_request = services.get_blood_request(request_id)
        return Response(BloodRequestSerializer(blood_request).data)


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

    def put(self, request, request_id):
        return reject_history_change()

    def patch(self, request, request_id):
        return reject_history_change()

    def delete(self, request, request_id):
        return reject_history_change()


class BloodRequestHistoryListView(APIView):
    """US-20: audit log of requests, optionally limited to a logged-date range."""

    permission_classes = [IsAuthenticated, IsCoordinator]

    def get(self, request):
        params = RequestHistoryQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        logged_from = params.validated_data.get("logged_from")
        logged_to = params.validated_data.get("logged_to")
        records = list(
            services.list_request_history(
                logged_from=logged_from,
                logged_to=logged_to,
            )
        )
        message = ""
        if logged_from and logged_to and not records:
            message = "No requests found for this period"
        return Response(
            {
                "requests": RequestAuditSerializer(records, many=True).data,
                "message": message,
            }
        )

    def put(self, request):
        return reject_history_change()

    def patch(self, request):
        return reject_history_change()

    def delete(self, request):
        return reject_history_change()


class BloodRequestMatchView(APIView):
    """Suggest compatible units without reserving or changing inventory."""

    permission_classes = [IsAuthenticated, IsCoordinator]

    def get(self, request, request_id):
        units = MatchedUnitSerializer(matching.match_blood_request(request_id), many=True).data
        services.record_match(request_id, units, request.user)
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


class BloodRequestReserveView(APIView):
    """US-16: reserve selected compatible units for a request."""

    permission_classes = [IsAuthenticated, IsCoordinator]

    def post(self, request, request_id):
        data = ReserveUnitsSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        blood_request, remaining = services.reserve_units(
            request_id, data.validated_data["unit_ids"], request.user
        )
        return Response(
            {**BloodRequestSerializer(blood_request).data, "remaining_quantity": remaining},
            status=status.HTTP_201_CREATED,
        )
