from django.utils import timezone
from rest_framework import serializers

from config.choices import BloodType

from .models import DonationIntervalRule, Donor


class ContactSerializer(serializers.Serializer):
    """Only contact fields are exposed, never credentials or other donors' data."""

    donor_id = serializers.IntegerField(source="pk", read_only=True)
    email = serializers.EmailField(source="user.email", read_only=True)
    phone = serializers.CharField(read_only=True)


class ContactUpdateSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254, required=False)
    phone = serializers.RegexField(
        regex=r"\A[0-9]{10}\Z",
        required=False,
        trim_whitespace=False,
        error_messages={"invalid": "Phone number must be exactly 10 digits."},
    )

    def to_internal_value(self, data):
        # DRF normally ignores unknown keys. Reject them so callers cannot think
        # that role, ownership, password or blood type were changed by this endpoint.
        if isinstance(data, dict):
            unexpected = set(data) - set(self.fields)
            if unexpected:
                raise serializers.ValidationError(
                    {key: ["Only email and phone may be updated."] for key in sorted(unexpected)}
                )
        return super().to_internal_value(data)

    def validate_email(self, value):
        return value.lower()

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Provide an email or phone number to update.")
        return attrs


class DonorSearchParamsSerializer(serializers.Serializer):
    """Optional filters for coordinator donor search (US-08)."""

    name = serializers.CharField(required=False, allow_blank=False, max_length=200)
    email = serializers.CharField(required=False, allow_blank=False, max_length=254)
    blood_type = serializers.ChoiceField(required=False, choices=BloodType.choices)


class DonorRecordSerializer(serializers.ModelSerializer):
    """Public donor profile fields returned to coordinators."""

    email = serializers.EmailField(source="user.email", read_only=True)

    class Meta:
        model = Donor
        fields = [
            "id",
            "full_name",
            "email",
            "date_of_birth",
            "blood_type",
            "phone",
            "status",
            "created_at",
        ]
        read_only_fields = fields


class DonorRecordUpdateSerializer(serializers.Serializer):
    """Fields a coordinator may edit; account role and donation data are excluded."""

    full_name = serializers.CharField(required=False, max_length=200)
    email = serializers.EmailField(required=False, max_length=254)
    date_of_birth = serializers.DateField(required=False)
    blood_type = serializers.ChoiceField(required=False, choices=BloodType.choices)
    phone = serializers.RegexField(
        regex=r"\A[0-9]{10}\Z",
        required=False,
        trim_whitespace=False,
        error_messages={"invalid": "Phone number must be exactly 10 digits."},
    )

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unexpected = set(data) - set(self.fields)
            if unexpected:
                raise serializers.ValidationError(
                    {key: ["This field cannot be changed here."] for key in sorted(unexpected)}
                )
        return super().to_internal_value(data)

    def validate_email(self, value):
        return value.lower()

    def validate_date_of_birth(self, value):
        from accounts.serializers import DonorRegistrationSerializer

        return DonorRegistrationSerializer().validate_date_of_birth(value)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Provide at least one donor field to update.")
        return attrs


class DonationCreateSerializer(serializers.Serializer):
    """US-09"""

    donation_type = serializers.SlugRelatedField(
        slug_field="donation_type",
        queryset=DonationIntervalRule.objects.all(),
        error_messages={"does_not_exist": "Unknown donation type: {value}."},
    )
    donation_date = serializers.DateField()
    blood_type = serializers.ChoiceField(choices=BloodType.choices)
    volume_ml = serializers.IntegerField(min_value=1)

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unexpected = set(data) - set(self.fields)
            if unexpected:
                raise serializers.ValidationError(
                    {key: ["This field cannot be set here."] for key in sorted(unexpected)}
                )
        return super().to_internal_value(data)

    def validate_donation_date(self, value):
        # The blood bank's local date , as in US-04.
        if value > timezone.localdate():
            raise serializers.ValidationError("Donation date cannot be in the future.")
        return value
