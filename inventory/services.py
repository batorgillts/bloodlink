"""Rules for Inventory Management that change a unit's state (US-17).

Views call these functions; these functions never deal with HTTP.
"""

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from config.exceptions import Conflict
from request import services as request_services

from .models import BloodUnit

RESERVED_WARNING = (
    "This unit is reserved for request {request_id}. "
    "Discarding it will reduce that request's reserved units."
)


class ConfirmationRequired(Exception):
    """AC4: the unit is reserved; the view answers 409 with the warning and request ID."""

    def __init__(self, request_id):
        super().__init__(RESERVED_WARNING.format(request_id=request_id))
        self.request_id = request_id


@transaction.atomic
def discard_unit(unit_id, *, reason, confirm, coordinator):
    """US-17: mark a unit Discarded with a reason; returns (unit, affected request or None).

    Discard and the reservation release happen in one transaction (Sprint 2 C4
    decision), so a unit is never discarded while its request still counts it.
    """
    if not BloodUnit.objects.filter(pk=unit_id).exists():
        raise NotFound("Blood unit not found.")

    # Same lock order as cancelling a request (US-19): request first, then the unit.
    locked_request = request_services.lock_request_reserving_unit(unit_id)
    unit = BloodUnit.objects.select_for_update().get(pk=unit_id)

    # AC6 / design: Discarded is final.
    if unit.status == BloodUnit.Status.DISCARDED:
        raise Conflict("This unit is already discarded.")

    # Sprint 2 state machine: an expired unit is discarded with the reason Expired.
    expired = unit.effective_status == BloodUnit.Status.EXPIRED
    if expired and reason != BloodUnit.DiscardReason.EXPIRED:
        raise ValidationError(
            {"reason": ["This unit has expired, so the discard reason must be Expired."]}
        )

    # AC4: a reserved unit is discarded only after the coordinator confirms the warning.
    if locked_request is not None and not confirm:
        raise ConfirmationRequired(locked_request.pk)

    discarded_at = timezone.now()
    affected_request = request_services.release_reservation_for_discard(
        unit, coordinator, discarded_at, locked_request
    )

    unit.status = BloodUnit.Status.DISCARDED
    unit.discard_reason = reason
    unit.discarded_at = discarded_at
    unit.discarded_by = coordinator
    unit.save(update_fields=["status", "discard_reason", "discarded_at", "discarded_by"])
    return unit, affected_request
