"""Blood request operations for US-11, US-16 and US-19."""

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from config.exceptions import Conflict
from inventory.models import BloodUnit

from . import repository
from .models import BloodRequest, RequestEvent, Reservation


def list_blood_requests():
    return repository.list_blood_requests()


@transaction.atomic
def log_blood_request(data, coordinator):
    # Status and logging metadata are assigned by the server, not the client.
    blood_request = repository.create_blood_request(logged_by=coordinator, **data)
    repository.create_request_event(
        request=blood_request,
        event_type=RequestEvent.EventType.LOGGED,
        to_status=blood_request.status,
        actor=coordinator,
    )
    return blood_request


@transaction.atomic
def cancel_blood_request(request_id, coordinator):
    blood_request = repository.request_for_update(request_id)
    if blood_request is None:
        raise NotFound("Blood request not found.")
    if blood_request.status == BloodRequest.Status.FULFILLED:
        raise Conflict("Fulfilled requests cannot be cancelled.")
    if blood_request.status == BloodRequest.Status.CANCELLED:
        raise Conflict("Cancelled requests cannot be cancelled.")
    if not blood_request.can_cancel:
        raise Conflict("This blood request cannot be cancelled.")

    previous_status = blood_request.status
    cancelled_at = timezone.now()
    released_units = 0

    for reservation in repository.active_reservations_for_update(blood_request.pk):
        unit = repository.unit_for_update(reservation.unit_id)
        if unit.status != BloodUnit.Status.DISCARDED:
            unit.status = (
                BloodUnit.Status.EXPIRED
                if unit.status == BloodUnit.Status.EXPIRED or unit.expires_at <= cancelled_at
                else BloodUnit.Status.AVAILABLE
            )
            repository.save_unit_status(unit)

        reservation.released_at = cancelled_at
        reservation.release_reason = Reservation.ReleaseReason.CANCELLED
        repository.save_reservation_release(reservation)
        repository.create_request_event(
            request=blood_request,
            event_type=RequestEvent.EventType.RELEASED,
            unit=unit,
            created_at=cancelled_at,
            actor=coordinator,
        )
        released_units += 1

    blood_request.status = BloodRequest.Status.CANCELLED
    repository.save_request_status(blood_request)
    repository.create_request_event(
        request=blood_request,
        event_type=RequestEvent.EventType.STATUS_CHANGED,
        from_status=previous_status,
        to_status=BloodRequest.Status.CANCELLED,
        created_at=cancelled_at,
        actor=coordinator,
    )
    return blood_request, released_units


def lock_request_reserving_unit(unit_id):
    reservation = repository.active_reservation_for_unit(unit_id)
    if reservation is None:
        return None
    return repository.request_for_update(reservation.request_id)


def release_reservation_for_discard(unit, coordinator, released_at, locked_request):

    reservation = repository.active_reservation_for_unit(unit.pk, lock=True)
    if reservation is None:
        return None
    if locked_request is None or reservation.request_id != locked_request.pk:
        # Reserved for a different request between our two reads: ask to retry.
        raise Conflict("This unit's reservation just changed. Please try again.")

    reservation.released_at = released_at
    reservation.release_reason = Reservation.ReleaseReason.DISCARDED
    repository.save_reservation_release(reservation)
    repository.create_request_event(
        request=locked_request,
        event_type=RequestEvent.EventType.RELEASED,
        unit=unit,
        created_at=released_at,
        actor=coordinator,
    )


    previous_status = locked_request.status
    remaining = repository.count_active_reservations(locked_request.pk)
    new_status = (
        BloodRequest.Status.PARTIALLY_FULFILLED if remaining else BloodRequest.Status.PENDING
    )
    if new_status != previous_status:
        locked_request.status = new_status
        repository.save_request_status(locked_request)
        repository.create_request_event(
            request=locked_request,
            event_type=RequestEvent.EventType.STATUS_CHANGED,
            from_status=previous_status,
            to_status=new_status,
            created_at=released_at,
            actor=coordinator,
        )
    return locked_request


def get_request_history(request_id):
    if not repository.find_request(request_id):
        raise NotFound("Blood request not found.")
    return repository.request_events(request_id)



@transaction.atomic
def reserve_units(request_id, unit_ids, coordinator):
    """US-16: hold the selected units for a request, all or nothing (Sprint 2 SQ-01).

    Locks the request first and then the units, the same order as cancel (US-19)
    and discard (US-17), so concurrent operations wait for each other instead of
    deadlocking. A second coordinator reserving the same unit waits for the first
    to commit, then sees the unit as reserved and gets 409.
    """
    blood_request = repository.request_for_update(request_id)
    if blood_request is None:
        raise NotFound("Blood request not found.")
    if blood_request.status not in (
        BloodRequest.Status.PENDING,
        BloodRequest.Status.PARTIALLY_FULFILLED,
    ):
        raise Conflict(f"Units cannot be reserved for a {blood_request.status} request.")

    # AC3: never reserve more units than the request still needs.
    already_reserved = repository.count_active_reservations(blood_request.pk)
    remaining = blood_request.quantity - already_reserved
    if len(unit_ids) > remaining:
        raise ValidationError(
            {"unit_ids": [f"Selected units exceed requested quantity ({remaining} still needed)."]}
        )

    units = repository.units_for_update(unit_ids)
    missing = set(unit_ids) - {unit.pk for unit in units}
    if missing:
        raise NotFound(f"Blood unit not found: {sorted(missing)}.")

    allowed_types = repository.compatible_unit_types(blood_request)
    now = timezone.now()
    for unit in units:
        if unit.component != blood_request.component or unit.blood_type not in allowed_types:
            raise ValidationError(
                {"unit_ids": [f"Unit {unit.unit_code} is not compatible with this request."]}
            )
        # AC4: checked after the lock, so a unit taken a moment ago is seen as taken.
        if unit.status != BloodUnit.Status.AVAILABLE or unit.expires_at <= now:
            raise Conflict(f"Unit {unit.unit_code} is no longer available.")

    try:
        for unit in units:
            repository.create_reservation(request=blood_request, unit=unit, reserved_by=coordinator)
            unit.status = BloodUnit.Status.RESERVED
            repository.save_unit_status(unit)
            repository.create_request_event(
                request=blood_request,
                event_type=RequestEvent.EventType.RESERVED,
                unit=unit,
                created_at=now,
                actor=coordinator,
            )
    except IntegrityError as exc:
        # Last line of defence: the database allows one active reservation per unit.
        raise Conflict("A selected unit is no longer available.") from exc

    previous_status = blood_request.status
    reserved_total = already_reserved + len(units)
    blood_request.status = (
        BloodRequest.Status.FULFILLED
        if reserved_total == blood_request.quantity
        else BloodRequest.Status.PARTIALLY_FULFILLED
    )
    if blood_request.status != previous_status:
        repository.save_request_status(blood_request)
        repository.create_request_event(
            request=blood_request,
            event_type=RequestEvent.EventType.STATUS_CHANGED,
            from_status=previous_status,
            to_status=blood_request.status,
            created_at=now,
            actor=coordinator,
        )
    return blood_request, units, blood_request.quantity - reserved_total