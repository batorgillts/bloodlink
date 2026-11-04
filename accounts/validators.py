from django.core.exceptions import ValidationError


class ContainsNumberValidator:
    """US-01: the password must include at least one number."""

    def validate(self, password, user=None):
        if not any(ch.isdigit() for ch in password):
            raise ValidationError(
                "Password must include at least one number.", code="password_no_number"
            )

    def get_help_text(self):
        return "Your password must include at least one number."
