from rest_framework import serializers

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
