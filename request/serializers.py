from rest_framework import serializers

from config.choices import Component
from inventory.models import BloodUnit

from .models import BloodRequest, RequestEvent


class BloodRequestSerializer(serializers.ModelSerializer):
    quantity = serializers.IntegerField(min_value=1)
    can_cancel = serializers.BooleanField(read_only=True)

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
            "can_cancel",
        ]
        read_only_fields = ["id", "status", "logged_at", "logged_by"]


class ConfirmCancelSerializer(serializers.Serializer):
    confirm = serializers.BooleanField(required=True)

    def validate_confirm(self, value):
        if not value:
            raise serializers.ValidationError("Cancellation must be confirmed.")
        return value


class RequestEventSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source="actor.email", read_only=True)

    class Meta:
        model = RequestEvent
        fields = [
            "id",
            "event_type",
            "from_status",
            "to_status",
            "unit",
            "matched_unit_codes",
            "created_at",
            "actor",
            "actor_email",
        ]
        read_only_fields = fields


class MatchedUnitSerializer(serializers.ModelSerializer):
    is_identical = serializers.BooleanField(read_only=True)

    class Meta:
        model = BloodUnit
        fields = ["id", "unit_code", "blood_type", "component", "expires_at", "is_identical"]
        read_only_fields = fields

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.component == Component.PLATELETS:
            data["match_label"] = (
                "ABO-identical" if instance.is_identical else "ABO-compatible, not identical"
            )
        return data
