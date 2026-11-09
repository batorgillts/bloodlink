from django.conf import settings
from django.db import models
from django.db.models import Q
from django.utils import timezone

from config.choices import BloodType, Component
from inventory.models import BloodUnit


class BloodRequest(models.Model):
    """An incoming request for blood (Sprint 2 ER diagram: BLOOD_REQUEST)."""

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        PARTIALLY_FULFILLED = "partially_fulfilled", "Partially fulfilled"
        FULFILLED = "fulfilled", "Fulfilled"
        CANCELLED = "cancelled", "Cancelled"

    blood_type = models.CharField(max_length=3, choices=BloodType.choices)
    component = models.CharField(max_length=10, choices=Component.choices)
    quantity = models.PositiveIntegerField()
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    logged_at = models.DateTimeField(auto_now_add=True)
    logged_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="logged_blood_requests",
    )

    class Meta:
        ordering = ["-logged_at", "-id"]
        constraints = [
            models.CheckConstraint(
                condition=Q(blood_type__in=BloodType.values),
                name="bloodrequest_blood_type_valid",
            ),
            models.CheckConstraint(
                condition=Q(component__in=Component.values),
                name="bloodrequest_component_valid",
            ),
            models.CheckConstraint(
                condition=Q(quantity__gt=0),
                name="bloodrequest_quantity_positive",
            ),
            models.CheckConstraint(
                condition=Q(
                    status__in=["pending", "partially_fulfilled", "fulfilled", "cancelled"]
                ),
                name="bloodrequest_status_valid",
            ),
        ]
        indexes = [
            models.Index(
                fields=["status", "blood_type", "component", "-logged_at"],
                name="request_filter_idx",
            ),
        ]

    def __str__(self):
        return f"{self.blood_type} {self.component} request ({self.quantity})"

    @property
    def can_cancel(self):
        return self.status in (self.Status.PENDING, self.Status.PARTIALLY_FULFILLED)


class Reservation(models.Model):
    """A blood unit held for a request until it is released."""

    class ReleaseReason(models.TextChoices):
        CANCELLED = "cancelled", "Cancelled"
        DISCARDED = "discarded", "Discarded"

    request = models.ForeignKey(
        BloodRequest, on_delete=models.PROTECT, related_name="reservations"
    )
    unit = models.ForeignKey(
        BloodUnit, on_delete=models.PROTECT, related_name="reservations"
    )
    reserved_at = models.DateTimeField(auto_now_add=True)
    reserved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="blood_reservations",
    )
    released_at = models.DateTimeField(null=True, blank=True)
    release_reason = models.CharField(
        max_length=10, choices=ReleaseReason.choices, blank=True, default=""
    )

    class Meta:
        ordering = ["reserved_at", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["unit"],
                condition=Q(released_at__isnull=True),
                name="reservation_one_active_unit",
            ),
            models.CheckConstraint(
                condition=(
                    Q(released_at__isnull=True, release_reason="")
                    | Q(
                        released_at__isnull=False,
                        release_reason__in=["cancelled", "discarded"],
                    )
                ),
                name="reservation_release_reason_valid",
            ),
        ]


class RequestEvent(models.Model):
    """Append-only history for blood request activity."""

    class EventType(models.TextChoices):
        LOGGED = "logged", "Logged"
        MATCHED = "matched", "Matched"
        RESERVED = "reserved", "Reserved"
        RELEASED = "released", "Released"
        STATUS_CHANGED = "status_changed", "Status changed"

    request = models.ForeignKey(
        BloodRequest, on_delete=models.PROTECT, related_name="events"
    )
    event_type = models.CharField(max_length=20, choices=EventType.choices)
    from_status = models.CharField(
        max_length=20, choices=BloodRequest.Status.choices, blank=True, default=""
    )
    to_status = models.CharField(
        max_length=20, choices=BloodRequest.Status.choices, blank=True, default=""
    )
    unit = models.ForeignKey(
        BloodUnit,
        on_delete=models.PROTECT,
        related_name="request_events",
        null=True,
        blank=True,
    )
    matched_unit_codes = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="request_events",
    )

    class Meta:
        ordering = ["created_at", "id"]
