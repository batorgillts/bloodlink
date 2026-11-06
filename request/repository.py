"""Database operations for blood request records and reservations."""

from inventory.models import BloodUnit

from .models import BloodRequest, RequestEvent, Reservation


def list_blood_requests():
    return BloodRequest.objects.select_related("logged_by").all()


def create_blood_request(*, logged_by, blood_type, component, quantity):
    return BloodRequest.objects.create(
        logged_by=logged_by,
        blood_type=blood_type,
        component=component,
        quantity=quantity,
    )


def request_for_update(request_id):
    return BloodRequest.objects.select_for_update().filter(pk=request_id).first()


def find_request(request_id):
    return BloodRequest.objects.filter(pk=request_id).first()


def active_reservations_for_update(request_id):
    return list(
        Reservation.objects.select_for_update()
        .filter(request_id=request_id, released_at__isnull=True)
        .order_by("id")
    )


def unit_for_update(unit_id):
    return BloodUnit.objects.select_for_update().get(pk=unit_id)


def save_request_status(blood_request):
    blood_request.save(update_fields=["status"])


def save_reservation_release(reservation):
    reservation.save(update_fields=["released_at", "release_reason"])


def save_unit_status(unit):
    unit.save(update_fields=["status"])


def create_request_event(**fields):
    return RequestEvent.objects.create(**fields)


def request_events(request_id):
    return RequestEvent.objects.filter(request_id=request_id).select_related("actor", "unit")
