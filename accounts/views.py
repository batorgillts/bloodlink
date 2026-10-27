"""Request layer for Authentication & Access."""

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .serializers import DonorRegistrationSerializer


class DonorRegistrationView(APIView):
    """POST /api/auth/register/ (US-01). Open to unregistered visitors.

    201: account created and signed in (returns access and refresh tokens)
    400: missing or invalid field (age under 17, weak password, bad phone, ...)
    409: email already registered
    """

    permission_classes = [AllowAny]
    authentication_classes = []  # visitors have no token yet; also avoids CSRF checks

    def post(self, request):
        data = DonorRegistrationSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user, tokens = services.register_donor(**data.validated_data)
        return Response(
            {"email": user.email, "role": user.role, **tokens}, status=status.HTTP_201_CREATED
        )
