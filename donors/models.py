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


class DonationIntervalRule(models.Model):
    """Minimum days between donations of one type (US-04, configured, not hardcoded)."""

    donation_type = models.CharField(max_length=32, unique=True)
    min_interval_days = models.PositiveIntegerField()

    class Meta:
        ordering = ["id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(min_interval_days__gte=1),
                name="donation_interval_days_positive",
            ),
        ]

    def __str__(self):
        return f"{self.donation_type} ({self.min_interval_days} days)"


class Donation(models.Model):
    """One donation entry (ER: DONATION). The next eligible date is calculated, not stored."""

    donor = models.ForeignKey(Donor, on_delete=models.PROTECT, related_name="donations")
    # The column stores the rule's donation_type code (ER: FK donation_type).
    donation_type = models.ForeignKey(
        DonationIntervalRule,
        to_field="donation_type",
        db_column="donation_type",
        on_delete=models.PROTECT,
        related_name="donations",
    )
    donation_date = models.DateField()
    blood_type = models.CharField(max_length=3, choices=BloodType.choices)
    volume_ml = models.PositiveIntegerField()
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="recorded_donations",
    )

    class Meta:
        ordering = ["-donation_date", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(blood_type__in=BloodType.values),
                name="donation_blood_type_valid",
            ),
            models.CheckConstraint(
                condition=Q(volume_ml__gte=1),
                name="donation_volume_positive",
            ),
        ]
        indexes = [
            models.Index(
                fields=["donor", "donation_type", "donation_date"],
                name="donation_donor_type_date",
            ),
        ]

    def __str__(self):
        return f"{self.donor_id} {self.donation_type_id} {self.donation_date}"
