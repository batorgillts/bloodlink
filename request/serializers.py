from rest_framework import serializers

from inventory.models import BloodUnit

from .models import BloodRequest


class BloodRequestSerializer(serializers.ModelSerializer):
    quantity = serializers.IntegerField(min_value=1)

    class Meta:
        model = BloodRequest
        fields = [
            "id",
            "blood_type",
            "component",
            "quantity",
            "status",
            "logged_at",
            "logged_by",
        ]
        read_only_fields = ["id", "status", "logged_at", "logged_by"]


class MatchedUnitSerializer(serializers.ModelSerializer):
    is_identical = serializers.BooleanField(read_only=True)

    class Meta:
        model = BloodUnit
        fields = ["id", "unit_code", "blood_type", "component", "expires_at", "is_identical"]
        read_only_fields = fields
