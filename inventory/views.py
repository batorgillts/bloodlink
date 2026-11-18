from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsCoordinator
from config.exceptions import Conflict
from config.search import filter_text

from . import services
from .choices import BloodType, Component
from .models import BloodUnit
from .serializers import (
    BloodUnitSerializer,
    BloodUnitUpdateSerializer,
    DiscardUnitSerializer,
    InventorySearchParamsSerializer,
)

FILTERS = {
    "blood_type": BloodType.values,
    "component": Component.values,
    "status": BloodUnit.Status.values,
}


class BloodUnitListCreate(generics.ListCreateAPIView):
    """US-07: record a blood unit and view inventory (coordinator only)."""

    serializer_class = BloodUnitSerializer
    permission_classes = [IsAuthenticated, IsCoordinator]

    def get_queryset(self):
        queryset = BloodUnit.objects.select_related("donation__donor__user")
        params = InventorySearchParamsSerializer(data=self.request.query_params)
        params.is_valid(raise_exception=True)
        queryset = filter_text(queryset, params.validated_data.get("search"), [
            "unit_code", "donation__donor__full_name", "donation__donor__user__email",
        ])
        for field, allowed in FILTERS.items():
            value = self.request.query_params.get(field)
            if value is None:
                continue
            if value not in allowed:
                raise ValidationError({field: f"Invalid filter. Allowed: {', '.join(allowed)}"})
            queryset = self.filter_by(queryset, field, value)
        return queryset

    @staticmethod
    def filter_by(queryset, field, value):
        if field != "status":
            return queryset.filter(**{field: value})
        # A unit past its expiry is expired even if its stored status still says
        # available, so the status filter uses the effective status (AC2).
        now = timezone.now()
        if value == BloodUnit.Status.AVAILABLE:
            return queryset.usable()
        if value == BloodUnit.Status.EXPIRED:
            return queryset.filter(
                Q(status=BloodUnit.Status.EXPIRED)
                | Q(status=BloodUnit.Status.AVAILABLE, expires_at__lte=now)
            )
        return queryset.filter(status=value)

    def perform_create(self, serializer):
        try:
            serializer.save()
        except IntegrityError as exc:
            # Two coordinators submitting the same unit ID at the same moment.
            raise Conflict("A unit with this ID already exists.") from exc


class BloodUnitDetail(generics.RetrieveAPIView):
    """View one unit; can_discard is false once it is Discarded"""

    queryset = BloodUnit.objects.select_related("donation__donor__user")
    serializer_class = BloodUnitSerializer
    permission_classes = [IsAuthenticated, IsCoordinator]
    lookup_url_kwarg = "unit_id"

    def patch(self, request, unit_id):
        data = BloodUnitUpdateSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        unit = services.update_unit(unit_id, data.validated_data, request.user)
        return Response(BloodUnitSerializer(unit).data)


class BloodUnitDiscard(APIView):
    """discard a unit with a reason; a reserved unit needs confirm: true."""

    permission_classes = [IsAuthenticated, IsCoordinator]

    def post(self, request, unit_id):
        data = DiscardUnitSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        try:
            unit, affected_request = services.discard_unit(
                unit_id, coordinator=request.user, **data.validated_data
            )
        except services.ConfirmationRequired as warning:
            return Response(
                {
                    "detail": str(warning),
                    "request_id": warning.request_id,
                    "confirm_required": True,
                },
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            {
                "unit": BloodUnitSerializer(unit).data,
                "request": (
                    {"id": affected_request.pk, "status": affected_request.status}
                    if affected_request
                    else None
                ),
            }
        )
