from django.utils import timezone
from rest_framework import serializers

from config.exceptions import Conflict

from .models import BloodUnit


# Serializer for BloodUnit model, used in API endpoints.
# read only, so client cannot ype in an expiry
class BloodUnitSerializer(serializers.ModelSerializer):
    effective_status = serializers.CharField(read_only=True)

    class Meta:
        model = BloodUnit
        fields = [
            "id",
            "unit_code",
            "blood_type",
            "component",
            "collected_at",
            "expires_at",
            "status",
            "effective_status",
        ]
        read_only_fields = ["expires_at", "status"]
        # We check uniqueness ourselves so a duplicate returns 409, not 400.
        extra_kwargs = {"unit_code": {"validators": []}}

    def validate_unit_code(self, value):
        value = value.strip().upper()
        if BloodUnit.objects.filter(unit_code=value).exists():
            raise Conflict(f"A unit with ID {value} already exists.")
        return value

    def validate_collected_at(self, value):
        if value > timezone.now():
            raise serializers.ValidationError("Collection time cannot be in the future.")
        return value
