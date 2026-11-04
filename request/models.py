from django.conf import settings
from django.db import models
from django.db.models import Q

from config.choices import BloodType, Component


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
