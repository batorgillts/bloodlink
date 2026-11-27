from rest_framework import serializers

from config.choices import BloodType, Component
from inventory.models import BloodUnit

from .models import BloodRequest, RequestEvent, Reservation

ALLOWED_REQUEST_STATUSES = ", ".join(BloodRequest.Status.values)


class BloodRequestListParamsSerializer(serializers.Serializer):
    status = serializers.ListField(
        child=serializers.ChoiceField(
            choices=BloodRequest.Status.choices,
            error_messages={
                "invalid_choice": f"Invalid filter. Allowed: {ALLOWED_REQUEST_STATUSES}"
            },
        ),
        required=False,
    )


class ReservedUnitSerializer(serializers.ModelSerializer):
    """US-16: a unit currently held for a request."""

    unit_id = serializers.IntegerField(source="unit.id")
    unit_code = serializers.CharField(source="unit.unit_code")
    blood_type = serializers.CharField(source="unit.blood_type")
    component = serializers.CharField(source="unit.component")
    expires_at = serializers.DateTimeField(source="unit.expires_at")

    class Meta:
        model = Reservation
        fields = ["unit_id", "unit_code", "blood_type", "component", "expires_at", "reserved_at"]
        read_only_fields = fields


class BloodRequestSerializer(serializers.ModelSerializer):
    quantity = serializers.IntegerField(min_value=1)
    can_cancel = serializers.BooleanField(read_only=True)
    reserved_units = serializers.SerializerMethodField()

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
            "reserved_units",
        ]
        read_only_fields = ["id", "status", "logged_at", "logged_by"]

    def get_reserved_units(self, blood_request):
        # Filled by repository.with_reserved_units(); a new request has no reservations yet.
        reservations = getattr(blood_request, "active_reservations", [])
        return ReservedUnitSerializer(reservations, many=True).data


class ConfirmCancelSerializer(serializers.Serializer):
    confirm = serializers.BooleanField(required=True)

    def validate_confirm(self, value):
        if not value:
            raise serializers.ValidationError("Cancellation must be confirmed.")
        return value


class ReserveUnitsSerializer(serializers.Serializer):
    """US-16 input: the units the coordinator picked from the match results."""

    unit_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), allow_empty=False)

    def validate_unit_ids(self, value):
        if len(value) != len(set(value)):
            raise serializers.ValidationError("Each unit can be selected only once.")
        return value


class RequestEventSerializer(serializers.ModelSerializer):
    actor_email = serializers.EmailField(source="actor.email", read_only=True)
    actor_name = serializers.SerializerMethodField()
    unit_code = serializers.SerializerMethodField()

    class Meta:
        model = RequestEvent
        fields = [
            "id",
            "event_type",
            "from_status",
            "to_status",
            "unit",
            "unit_code",
            "matched_unit_codes",
            "created_at",
            "actor",
            "actor_email",
            "actor_name",
        ]
        read_only_fields = fields

    def get_actor_name(self, event):
        name = event.actor.get_full_name().strip()
        return name or event.actor.email

    def get_unit_code(self, event):
        return event.unit.unit_code if event.unit_id else ""


class RequestHistoryQuerySerializer(serializers.Serializer):
    """US-20: optional request details and inclusive logged-date range."""

    logged_from = serializers.DateField(required=False)
    logged_to = serializers.DateField(required=False)
    blood_type = serializers.ChoiceField(choices=BloodType.choices, required=False)
    component = serializers.ChoiceField(choices=Component.choices, required=False)
    quantity = serializers.IntegerField(min_value=1, required=False)

    def validate(self, attrs):
        start = attrs.get("logged_from")
        end = attrs.get("logged_to")
        if (start is None) != (end is None):
            raise serializers.ValidationError("Enter both a start date and an end date.")
        if start and end and start > end:
            raise serializers.ValidationError(
                "The start date must be on or before the end date."
            )
        return attrs


class RequestAuditSerializer(serializers.ModelSerializer):
    """US-20: one request plus the append-only events that explain how it was handled."""

    coordinator = serializers.SerializerMethodField()
    events = RequestEventSerializer(many=True, read_only=True)

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
            "coordinator",
            "events",
        ]
        read_only_fields = fields

    def get_coordinator(self, blood_request):
        name = blood_request.logged_by.get_full_name().strip()
        return name or blood_request.logged_by.email


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
