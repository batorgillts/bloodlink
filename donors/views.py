from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .permissions import IsDonor
from .serializers import ContactSerializer, ContactUpdateSerializer


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
