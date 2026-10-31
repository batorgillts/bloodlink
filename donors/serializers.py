from rest_framework import serializers


class DeleteConfirmationSerializer(serializers.Serializer):
    """Destructive requests require an explicit JSON boolean, not a truthy string."""

    confirm = serializers.BooleanField()

    def to_internal_value(self, data):
        if not isinstance(data, dict) or data.get("confirm") is not True:
            raise serializers.ValidationError({"confirm": ["Send confirm as JSON true."]})
        if set(data) != {"confirm"}:
            raise serializers.ValidationError({"non_field_errors": ["Only confirm is accepted."]})
        return super().to_internal_value(data)


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
