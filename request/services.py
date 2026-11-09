"""Blood request operations for US-11 and US-19."""

from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound

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


def get_request_history(request_id):
    if not repository.find_request(request_id):
        raise NotFound("Blood request not found.")
    return repository.request_events(request_id)
