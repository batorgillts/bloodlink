from datetime import timezone as datetime_timezone

from django.utils import timezone
from rest_framework import serializers

from config.exceptions import Conflict
from donors.models import DonationIntervalRule

from .models import BloodUnit, ShelfLifeRule, StockThreshold


class InventorySearchParamsSerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True, max_length=254)


# Serializer for BloodUnit model, used in API endpoints.
# read only, so client cannot ype in an expiry
class BloodUnitSerializer(serializers.ModelSerializer):
    # UTC also keeps very old test dates parseable by browsers: historical local
    # time-zone offsets may contain seconds, which JavaScript ISO parsing rejects.
    collected_at = serializers.DateTimeField(default_timezone=datetime_timezone.utc)
    expires_at = serializers.DateTimeField(read_only=True, default_timezone=datetime_timezone.utc)
    effective_status = serializers.CharField(read_only=True)
    can_discard = serializers.BooleanField(read_only=True)
    can_edit = serializers.BooleanField(read_only=True)
    donor_id = serializers.IntegerField(min_value=1, write_only=True)
    donation_id = serializers.IntegerField(min_value=1, required=False)
    donation_type = serializers.SlugRelatedField(
        slug_field="donation_type", queryset=DonationIntervalRule.objects.all(),
        required=False, write_only=True,
    )
    volume_ml = serializers.IntegerField(min_value=1, required=False, write_only=True)
    source_donation = serializers.SerializerMethodField()

    def get_source_donation(self, unit):
        if unit.donation_id is None:
            return None
        donation = unit.donation
        return {
            "id": donation.pk,
            "donor_id": donation.donor_id,
            "donor_name": donation.donor.full_name,
            "donor_email": donation.donor.user.email,
            "donation_type": donation.donation_type_id,
            "donation_date": donation.donation_date,
        }

    def validate(self, attrs):
        if "donation_id" in attrs:
            if "donation_type" in attrs or "volume_ml" in attrs:
                raise serializers.ValidationError(
                    "Choose an existing donation OR provide a new donation type and volume."
                )
        elif "donation_type" not in attrs or "volume_ml" not in attrs:
            raise serializers.ValidationError(
                "Select a source donation, or provide donation type and volume for a new donation."
            )
        return attrs

    def create(self, validated_data):
        from .services import record_unit

        return record_unit(validated_data, self.context["request"].user)

    class Meta:
        model = BloodUnit
        fields = [
            "id",
            "donor_id",
            "donation_id",
            "donation_type",
            "volume_ml",
            "source_donation",
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
            "can_edit",
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


class BloodUnitUpdateSerializer(serializers.Serializer):
    component = serializers.ChoiceField(
        choices=BloodUnit._meta.get_field("component").choices, required=False,
    )
    collected_at = serializers.DateTimeField(required=False)
    donation_type = serializers.SlugRelatedField(
        slug_field="donation_type", queryset=DonationIntervalRule.objects.all(), required=False,
    )

    def to_internal_value(self, data):
        if not isinstance(data, dict):
            raise serializers.ValidationError("Send an object containing the fields to correct.")
        unexpected = set(data) - set(self.fields)
        if unexpected:
            raise serializers.ValidationError({key: ["This field cannot be changed here."]
                                               for key in sorted(unexpected)})
        return super().to_internal_value(data)

    def validate_collected_at(self, value):
        if value > timezone.now():
            raise serializers.ValidationError("Collection time cannot be in the future.")
        return value

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Provide at least one field to correct.")
        return attrs


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


THRESHOLD_MESSAGE = "The low-stock threshold must be a positive whole number."
WINDOW_MESSAGE = "The expiring-soon window must be a positive whole number of days."


class StockThresholdSerializer(serializers.ModelSerializer):
    """US-12: one low-stock threshold, with an optional expiring-soon override."""

    minimum_units = serializers.IntegerField(
        min_value=1,
        error_messages={
            "required": THRESHOLD_MESSAGE,
            "null": THRESHOLD_MESSAGE,
            "invalid": THRESHOLD_MESSAGE,
            "min_value": THRESHOLD_MESSAGE,
            "max_string_length": THRESHOLD_MESSAGE,
        },
    )
    expiring_soon_days = serializers.IntegerField(
        min_value=1,
        required=False,
        allow_null=True,
        error_messages={"invalid": WINDOW_MESSAGE, "min_value": WINDOW_MESSAGE},
    )

    class Meta:
        model = StockThreshold
        fields = [
            "id",
            "blood_type",
            "component",
            "minimum_units",
            "expiring_soon_days",
            "updated_at",
        ]
        read_only_fields = ["id", "updated_at"]
        # Saving is an upsert by blood type and component, so skip the unique check.
        validators = []

    def validate(self, attrs):
        days = attrs.get("expiring_soon_days")
        if days:
            shelf_life = (
                ShelfLifeRule.objects.filter(component=attrs["component"])
                .values_list("shelf_life_days", flat=True)
                .first()
            )
            if shelf_life and days >= shelf_life:
                raise serializers.ValidationError(
                    {
                        "expiring_soon_days": [
                            f"The expiring-soon window must be shorter than the "
                            f"{shelf_life}-day shelf life of this component."
                        ]
                    }
                )
        return attrs
