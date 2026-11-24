from datetime import timedelta

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
    # US-12: how many days before expiry a unit counts as "expiring soon". It follows
    # the component's shelf life (seeded by migration) and a threshold can override it.
    expiring_soon_days = models.PositiveIntegerField(default=7)

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
    # Nullable only for inventory recorded before source tracking was introduced.
    # Several processed units may come from the same donation.
    donation = models.ForeignKey(
        "donors.Donation", on_delete=models.PROTECT, null=True, blank=True,
        related_name="blood_units",
    )
    blood_type = models.CharField(max_length=3, choices=BloodType.choices)
    component = models.CharField(max_length=10, choices=Component.choices)
    collected_at = models.DateTimeField()
    expires_at = models.DateTimeField(editable=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.AVAILABLE)
    discard_reason = models.CharField(
        max_length=20, choices=DiscardReason.choices, blank=True, default=""
    )
    # wastage is recorded with when and by whom, not just the reason.
    discarded_at = models.DateTimeField(null=True, blank=True)
    discarded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="+",
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
            # Add days on the local wall clock (TIME_ZONE), so a unit collected at
            # 10:00 AM expires at 10:00 AM even across a daylight saving change (AC1).
            collected_local = timezone.localtime(self.collected_at)
            self.expires_at = collected_local + timedelta(days=rule.shelf_life_days)
        super().save(*args, **kwargs)

    @property
    def effective_status(self):
        """A unit past expiry reads as expired even before anyone updates its status."""
        if self.status == self.Status.AVAILABLE and self.expires_at <= timezone.now():
            return self.Status.EXPIRED
        return self.status

    @property
    def can_edit(self):
        return self.status in (self.Status.AVAILABLE, self.Status.EXPIRED)

    @property
    def can_discard(self):
        """the discard option is not offered again."""
        return self.status != self.Status.DISCARDED

    def __str__(self):
        return f"{self.unit_code} ({self.blood_type} {self.component})"


class CompatibilityRule(models.Model):
    """Configured unit-to-request compatibility, scoped to a component."""

    component = models.CharField(max_length=10, choices=Component.choices)
    request_blood_type = models.CharField(max_length=3, choices=BloodType.choices)
    unit_blood_type = models.CharField(max_length=3, choices=BloodType.choices)
    is_identical = models.BooleanField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["component", "request_blood_type", "unit_blood_type"],
                name="compatibility_rule_unique",
            ),
            models.CheckConstraint(
                condition=Q(component__in=Component.values),
                name="compatibility_component_valid",
            ),
            models.CheckConstraint(
                condition=Q(request_blood_type__in=BloodType.values),
                name="compatibility_request_type_valid",
            ),
            models.CheckConstraint(
                condition=Q(unit_blood_type__in=BloodType.values),
                name="compatibility_unit_type_valid",
            ),
        ]


class StockThreshold(models.Model):
    """US-12: a coordinator-set low-stock alert level for one blood type and component."""

    blood_type = models.CharField(max_length=3, choices=BloodType.choices)
    component = models.CharField(max_length=10, choices=Component.choices)
    minimum_units = models.PositiveIntegerField()
    # Optional override of the component's expiring-soon window; null = component default.
    expiring_soon_days = models.PositiveIntegerField(null=True, blank=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, related_name="+"
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["component", "blood_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["blood_type", "component"], name="stock_threshold_unique"
            ),
            # AC5: the database also refuses a threshold that is not positive.
            models.CheckConstraint(
                condition=Q(minimum_units__gte=1), name="stock_threshold_positive"
            ),
        ]

    def __str__(self):
        return f"{self.blood_type} {self.component}: alert below {self.minimum_units}"
