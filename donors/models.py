from django.conf import settings
from django.db import models
from django.db.models import Q

from config.choices import BloodType


class Donor(models.Model):
    """A donor's profile, linked to one User (Sprint 2 ER diagram: DONOR)."""

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        WITHDRAWN = "withdrawn", "Withdrawn"  # US-05
        DELETED = "deleted", "Deleted"  # US-10: soft delete, donation history is kept

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="donor"
    )
    full_name = models.CharField(max_length=200)
    # We store date of birth, not age (Sprint 2 data model decision).
    date_of_birth = models.DateField()
    blood_type = models.CharField(max_length=3, choices=BloodType.choices)
    phone = models.CharField(max_length=10)  # exactly 10 digits, checked by the serializer
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            # NFR-3: the database itself rejects values outside the allowed lists.
            models.CheckConstraint(
                condition=Q(status__in=["active", "withdrawn", "deleted"]),
                name="donor_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(blood_type__in=BloodType.values), name="donor_blood_type_valid"
            ),
        ]

    def __str__(self):
        return f"{self.full_name} ({self.blood_type})"
