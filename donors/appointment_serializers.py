from rest_framework import serializers

from config.choices import BloodType, Component

from .models import DonationAppointment, DonationIntervalRule


class AppointmentWriteSerializer(serializers.Serializer):
    donation_type = serializers.SlugRelatedField(
        slug_field="donation_type",
        queryset=DonationIntervalRule.objects.all(),
        error_messages={"does_not_exist": "Unknown donation type: {value}."},
    )
    appointment_date = serializers.DateField(input_formats=["%Y-%m-%d"])
    appointment_time = serializers.TimeField(input_formats=["%H:%M"])

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unexpected = set(data) - set(self.fields)
            if unexpected:
                raise serializers.ValidationError({
                    key: ["This field cannot be set here."] for key in sorted(unexpected)
                })
        return super().to_internal_value(data)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Provide an appointment field to update.")
        return attrs


class AppointmentSearchSerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True, max_length=254)
    donation_type = serializers.SlugRelatedField(
        slug_field="donation_type", queryset=DonationIntervalRule.objects.all(), required=False
    )
    blood_type = serializers.ChoiceField(choices=BloodType.choices, required=False)
    status = serializers.ChoiceField(choices=DonationAppointment.Status.choices, required=False)


class AppointmentRecordSerializer(serializers.Serializer):
    """The server derives donor identity and donation type from the locked booking."""

    unit_code = serializers.CharField(max_length=32)
    volume_ml = serializers.IntegerField(min_value=1)
    component = serializers.ChoiceField(choices=Component.choices)
    collected_date = serializers.DateField(input_formats=["%Y-%m-%d"])
    collected_time = serializers.TimeField(input_formats=["%H:%M"])

    def to_internal_value(self, data):
        if isinstance(data, dict):
            unexpected = set(data) - set(self.fields)
            if unexpected:
                raise serializers.ValidationError({
                    key: ["This field is determined by the appointment and cannot be set here."]
                    for key in sorted(unexpected)
                })
        return super().to_internal_value(data)


class StartAppointmentSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if not isinstance(data, dict) or data:
            raise serializers.ValidationError("Send an empty object to start the appointment.")
        return {}
