from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCoordinator
from accounts.serializers import DonorRegistrationSerializer

from . import services
from .permissions import CanViewEligibility, IsDonor
from .serializers import (
    ContactSerializer,
    ContactUpdateSerializer,
    DonationCreateSerializer,
    DonorRecordSerializer,
    DonorRecordUpdateSerializer,
    DonorSearchParamsSerializer,
)


class DonorContactView(APIView):
    """US-03: GET/PATCH the signed-in donor's contact information."""

    permission_classes = [IsAuthenticated, IsDonor]

    def get(self, request, donor_id=None):
        donor = services.get_own_contact(request.user.pk, donor_id)
        return Response(ContactSerializer(donor).data)

    def patch(self, request, donor_id=None):
        donor = services.get_own_contact(request.user.pk, donor_id)
        data = ContactUpdateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        donor = services.update_contact(donor, data.validated_data)
        return Response(ContactSerializer(donor).data)


class EligibilityView(APIView):
    """US-04: donation history and the next eligible date for each donation type."""

    permission_classes = [IsAuthenticated, CanViewEligibility]

    def get(self, request, donor_id=None):
        return Response(services.get_eligibility(request.user, donor_id))


class DonorRecordListCreateView(APIView):
    """US-08: coordinator donor search and walk-in registration."""

    permission_classes = [IsCoordinator]

    def get(self, request):
        params = DonorSearchParamsSerializer(data=request.query_params)
        if not params.is_valid():
            raise ValidationError(params.errors)
        donors = services.search_donor_records(params.validated_data)
        return Response(DonorRecordSerializer(donors, many=True).data)

    def post(self, request):
        data = DonorRegistrationSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        donor = services.create_walk_in_donor(data.validated_data)
        return Response(
            DonorRecordSerializer(donor).data,
            status=status.HTTP_201_CREATED,
        )


class DonorRecordDetailView(APIView):
    """US-08: coordinator views and edits one donor record."""

    permission_classes = [IsCoordinator]

    def get(self, request, donor_id):
        donor = services.get_donor_record(donor_id)
        eligibility = services.get_eligibility(request.user, donor_id)
        return Response({**DonorRecordSerializer(donor).data, **eligibility})

    def patch(self, request, donor_id):
        donor = services.get_donor_record(donor_id)
        data = DonorRecordUpdateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        donor = services.update_donor_record(donor, data.validated_data)
        return Response(DonorRecordSerializer(donor).data)



class DonationCreateView(APIView):
    """US-09 (as per sprint 2)
    201: saved;
    400: missing/invalid field, future date, not yet eligible, blood type mismatch
    403: caller is not a coordinator
    404: unknown donor
    409: donor not active
    """
    permission_classes = [IsCoordinator]



    def post(self, request, donor_id):
        data = DonationCreateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        result = services.record_donation(donor_id, data.validated_data, request.user)
        return Response(result, status=status.HTTP_201_CREATED)
