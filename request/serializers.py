from rest_framework import serializers

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
