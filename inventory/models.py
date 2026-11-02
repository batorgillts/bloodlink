from datetime import timedelta
from datetime import timezone as dt_timezone

from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from .choices import BloodType, Component


# its a table, not a constatntm because medical rules live in tables by Sprint 2
class ShelfLifeRule(models.Model):
    """Configured shelf life per component. Seeded by migration, not hard-coded."""

    component = models.CharField(max_length=10, choices=Component.choices, unique=True)
    shelf_life_days = models.PositiveIntegerField()

    def __str__(self):
        return f"{self.component}: {self.shelf_life_days} days"


class BloodUnitQuerySet(models.QuerySet):
    # NFR-4 checking exipry time
    def usable(self):
        """Available AND not past expiry (US-07). Every matching query goes through this."""
        return self.filter(status=BloodUnit.Status.AVAILABLE, expires_at__gt=timezone.now())


class BloodUnit(models.Model):
    """One bag in inventory (ER diagram: Blood unit)."""

    class Status(models.TextChoices):
        AVAILABLE = "available", "Available"
        RESERVED = "reserved", "Reserved"
        DISCARDED = "discarded", "Discarded"
        EXPIRED = "expired", "Expired"

    class DiscardReason(models.TextChoices):
        EXPIRED = "expired", "Expired"
        DAMAGED = "damaged", "Damaged"
        FAILED_TESTING = "failed_testing", "Failed testing"
        OTHER = "other", "Other"

    unit_code = models.CharField(max_length=32, unique=True)
    blood_type = models.CharField(max_length=3, choices=BloodType.choices)
    component = models.CharField(max_length=10, choices=Component.choices)
    collected_at = models.DateTimeField()
    expires_at = models.DateTimeField(editable=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.AVAILABLE)
    discard_reason = models.CharField(
        max_length=20, choices=DiscardReason.choices, blank=True, default=""
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = BloodUnitQuerySet.as_manager()

    class Meta:
        ordering = ["expires_at"]
        constraints = [
            # The database itself rejects any other status (NFR-3).
            models.CheckConstraint(
                condition=Q(status__in=["available", "reserved", "discarded", "expired"]),
                name="bloodunit_status_valid",
            ),
            models.CheckConstraint(
                condition=Q(blood_type__in=BloodType.values), name="bloodunit_blood_type_valid"
            ),
            models.CheckConstraint(
                condition=~Q(status="discarded") | ~Q(discard_reason=""),
                name="bloodunit_discard_requires_reason",
            ),
        ]
        indexes = [
            # Keeps matching fast at 10,000 units (NFR-4).
            models.Index(
                fields=["component", "blood_type", "status", "expires_at"], name="unit_match_idx"
            ),
        ]

    def save(self, *args, **kwargs):
        # Expiry is calculated from the shelf-life rule, never typed in (US-07).
        if self.expires_at is None:
            rule = ShelfLifeRule.objects.get(component=self.component)
            # Do the math in UTC: adding days to a local time that crosses a daylight
            # saving change would shift expiry by an hour.
            collected_utc = self.collected_at.astimezone(dt_timezone.utc)
            self.expires_at = collected_utc + timedelta(days=rule.shelf_life_days)
        super().save(*args, **kwargs)

    @property
    def effective_status(self):
        """A unit past expiry reads as expired even before anyone updates its status."""
        if self.status == self.Status.AVAILABLE and self.expires_at <= timezone.now():
            return self.Status.EXPIRED
        return self.status

    def __str__(self):
        return f"{self.unit_code} ({self.blood_type} {self.component})"
