from django.db import IntegrityError
from django.db.models import Q
from django.utils import timezone
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated

from accounts.permissions import IsCoordinator
from config.exceptions import Conflict

from .choices import BloodType, Component
from .models import BloodUnit
from .serializers import BloodUnitSerializer

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
        queryset = BloodUnit.objects.all()
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
            serializer.save(created_by=self.request.user)
        except IntegrityError as exc:
            # Two coordinators submitting the same unit ID at the same moment.
            raise Conflict("A unit with this ID already exists.") from exc
