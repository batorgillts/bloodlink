"""Rules for Inventory Management that change a unit's state (US-17).

Views call these functions; these functions never deal with HTTP.
"""

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from config.exceptions import Conflict
from donors import repository as donor_repository
from donors import services as donor_services
from donors.models import Donation
from request import services as request_services

from .models import BloodUnit


def validate_component(rule, component):
    if component not in rule.allowed_components:
        raise ValidationError({"component": [
            f"{component} is not configured for {rule.donation_type}. "
            "Choose a component supported by the source donation type."
        ]})


@transaction.atomic
def update_unit(unit_id, changes, coordinator):
    """Correct a unit and keep its source date, sibling units and expiry consistent."""
    from contextlib import nullcontext

    donor_services.ensure_coordinator(coordinator)
    original = BloodUnit.objects.select_related("donation").filter(pk=unit_id).first()
    if original is None:
        raise NotFound("Blood unit not found.")
    source_id = original.donation_id
    donor_lock = (donor_repository.locked_donor(original.donation.donor_id)
                  if source_id else nullcontext(None))
    with donor_lock as donor:
        donation = (Donation.objects.select_for_update().select_related("donation_type")
                    .get(pk=source_id) if source_id else None)
        # Lock sibling units in ID order before changing a shared source date or type.
        units = list(BloodUnit.objects.select_for_update().filter(
            **({"donation_id": source_id} if source_id else {"pk": unit_id})
        ).order_by("pk"))
        unit = next(u for u in units if u.pk == unit_id)
        if not unit.can_edit:
            raise Conflict("Reserved or discarded units cannot be edited.")
        new_time = changes.get("collected_at", unit.collected_at)
        new_component = changes.get("component", unit.component)
        if new_time > timezone.now():
            raise ValidationError({"collected_at": ["Collection time cannot be in the future."]})
        if donation:
            rule = changes.get("donation_type", donation.donation_type)
            new_date = timezone.localdate(new_time)
            donor_services.validate_donation_date(donor, new_date)
            source_changed = (new_date != donation.donation_date
                              or rule.pk != donation.donation_type.pk)
            if source_changed and any(not sibling.can_edit for sibling in units):
                raise Conflict(
                    "The source donation has reserved or discarded units. "
                    "Its date and donation type cannot be changed."
                )
            if source_changed:
                donor_services._check_interval(donor.pk, rule, new_date, exclude_id=donation.pk)
                for sibling in units:
                    validate_component(rule, new_component if sibling.pk == unit.pk
                                       else sibling.component)
            else:
                validate_component(rule, new_component)
            day_shift = new_date - donation.donation_date
            for sibling in units:
                if sibling.pk != unit.pk and day_shift.days:
                    sibling.collected_at = timezone.localtime(sibling.collected_at) + day_shift
                    if sibling.collected_at > timezone.now():
                        raise ValidationError({"collected_at": [
                            "This date would move another linked unit's collection into the future."
                        ]})
                    sibling.expires_at = None
                    if sibling.status == BloodUnit.Status.EXPIRED:
                        sibling.status = BloodUnit.Status.AVAILABLE
                    sibling.save()
            donation.donation_date = new_date
            donation.donation_type = rule
            donation.save(update_fields=["donation_date", "donation_type"])
        elif "donation_type" in changes:
            raise ValidationError({"donation_type": ["This unit has no source donation."]})
        unit.component = new_component
        unit.collected_at = new_time
        unit.expires_at = None
        if unit.status == BloodUnit.Status.EXPIRED:
            unit.status = BloodUnit.Status.AVAILABLE
        unit.save()
        return unit


@transaction.atomic
def record_unit(data, coordinator):
    """Save source donation and inventory together; never count a processed unit twice."""
    data = dict(data)
    donor_id = data.pop("donor_id")
    donation_id = data.pop("donation_id", None)
    rule = data.pop("donation_type", None)
    volume = data.pop("volume_ml", None)
    with donor_repository.locked_donor(donor_id) as donor:
        if donor is None:
            raise NotFound("Donor record not found.")
        donor_services.ensure_active_donor(donor)
        collection_date = timezone.localdate(data["collected_at"])
        if donation_id is not None:
            donation = donor_repository.locked_donation(donor_id, donation_id)
            if donation is None:
                raise ValidationError({"donation_id": ["Select a donation from this donor."]})
        else:
            result = donor_services.record_donation(donor_id, {
                "donation_type": rule,
                "donation_date": collection_date,
                "blood_type": data["blood_type"],
                "volume_ml": volume,
            }, coordinator)
            donation = Donation.objects.get(pk=result["donation"]["donation_id"])
        if data["blood_type"] != donation.blood_type:
            raise ValidationError({"blood_type": ["Must match the source donation's blood type."]})
        donor_services.validate_donation_date(donor, collection_date)
        validate_component(donation.donation_type, data["component"])
        if collection_date != donation.donation_date:
            raise ValidationError({"collected_at": [
                "Collection must be on the source donation date in the blood bank's "
                "time zone (America/New_York)."
            ]})
        return BloodUnit.objects.create(**data, donation=donation, created_by=coordinator)

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
