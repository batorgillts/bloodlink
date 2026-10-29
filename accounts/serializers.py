import re
from datetime import date

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from config.choices import BloodType

MIN_DONOR_AGE = 17  # US-01


def age_on(date_of_birth, today):
    """Whole years between date_of_birth and today."""
    had_birthday = (today.month, today.day) >= (date_of_birth.month, date_of_birth.day)
    return today.year - date_of_birth.year - (0 if had_birthday else 1)


class DonorRegistrationSerializer(serializers.Serializer):
    """Input for US-01. Any problem here is returned as HTTP 400 with a message per field."""

    full_name = serializers.CharField(max_length=200)
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)
    date_of_birth = serializers.DateField()
    blood_type = serializers.ChoiceField(choices=BloodType.choices)
    phone = serializers.CharField()

    def validate_email(self, value):
        return value.lower()

    def validate_password(self, value):
        # Runs every validator in AUTH_PASSWORD_VALIDATORS (8+ characters, at least one number).
        try:
            validate_password(value)
        except DjangoValidationError as err:
            raise serializers.ValidationError(list(err.messages))
        return value

    def validate_date_of_birth(self, value):
        today = date.today()
        if value > today:
            raise serializers.ValidationError("Date of birth cannot be in the future.")
        if age_on(value, today) < MIN_DONOR_AGE:
            raise serializers.ValidationError(
                f"You must be at least {MIN_DONOR_AGE} years old to register as a donor."
            )
        return value

    def validate_phone(self, value):
        if not re.fullmatch(r"[0-9]{10}", value):
            raise serializers.ValidationError("Phone number must be exactly 10 digits.")
        return value
