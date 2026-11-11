from django.utils import timezone
from rest_framework import serializers

from config.exceptions import Conflict

from .models import BloodUnit


# Serializer for BloodUnit model, used in API endpoints.
# read only, so client cannot ype in an expiry
class BloodUnitSerializer(serializers.ModelSerializer):
    effective_status = serializers.CharField(read_only=True)
    can_discard = serializers.BooleanField(read_only=True)

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
            "discard_reason",
            "discarded_at",
            "discarded_by",
            "can_discard",
        ]
        read_only_fields = [
            "expires_at",
            "status",
            "discard_reason",
            "discarded_at",
            "discarded_by",
        ]
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


REASON_REQUIRED = "A discard reason is required."
REASONS = {
    **{code: code for code in BloodUnit.DiscardReason.values},
    **{str(label).lower(): code for code, label in BloodUnit.DiscardReason.choices},
}


class DiscardUnitSerializer(serializers.Serializer):
    """US-17 input: a reason is required; confirm is needed only for a reserved unit."""

    reason = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    confirm = serializers.BooleanField(default=False)

    def validate(self, attrs):
        reason = (attrs.get("reason") or "").strip()
        if not reason:
            raise serializers.ValidationError({"reason": [REASON_REQUIRED]})
        code = REASONS.get(reason.lower())
        if code is None:
            allowed = ", ".join(str(label) for _, label in BloodUnit.DiscardReason.choices)
            raise serializers.ValidationError({"reason": [f"Choose one of: {allowed}."]})
        attrs["reason"] = code
        return attrs
