"""Database access for requests, reservations, history and compatible inventory."""

from django.db.models import Max, OuterRef, Q, Subquery

from donors.models import DonationIntervalRule, Donor
from inventory.models import BloodUnit, CompatibilityRule

from .models import BloodRequest, RequestEvent, Reservation


def list_blood_requests(*, status=None):
    requests = BloodRequest.objects.select_related("logged_by").all()
    if status is not None:
        requests = requests.filter(status=status)
    return requests


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


def active_reservation_for_unit(unit_id, *, lock=False):
    reservations = Reservation.objects.filter(unit_id=unit_id, released_at__isnull=True)
    if lock:
        reservations = reservations.select_for_update()
    return reservations.first()


def count_active_reservations(request_id):
    return Reservation.objects.filter(request_id=request_id, released_at__isnull=True).count()


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


def find_matching_request(request_id):
    return BloodRequest.objects.filter(pk=request_id).first()


def compatible_units(blood_request):
    rules = CompatibilityRule.objects.filter(
        component=blood_request.component,
        request_blood_type=blood_request.blood_type,
    )
    return (
        BloodUnit.objects.usable()
        .filter(
            component=blood_request.component,
            blood_type__in=rules.values("unit_blood_type"),
        )
        .annotate(
            is_identical=Subquery(
                rules.filter(unit_blood_type=OuterRef("blood_type")).values("is_identical")[:1]
            )
        )
        .order_by("-is_identical", "expires_at", "unit_code")
    )


def interval_days(donation_type):
    return (
        DonationIntervalRule.objects.filter(donation_type=donation_type)
        .values_list("min_interval_days", flat=True)
        .first()
    )


def compatible_donors(blood_request, donation_type):
    """US-18: active donors whose blood type the component's rules allow for this request.

    Each donor carries their latest donation of `donation_type` (for eligibility) and their
    latest donation of any type (shown to the coordinator).
    """
    rules = CompatibilityRule.objects.filter(
        component=blood_request.component,
        request_blood_type=blood_request.blood_type,
    )
    return (
        Donor.objects.filter(
            status=Donor.Status.ACTIVE,
            blood_type__in=rules.values("unit_blood_type"),
        )
        .select_related("user")
        .annotate(
            last_of_type=Max(
                "donations__donation_date",
                filter=Q(donations__donation_type_id=donation_type),
            ),
            last_donation_date=Max("donations__donation_date"),
            is_identical=Subquery(
                rules.filter(unit_blood_type=OuterRef("blood_type")).values("is_identical")[:1]
            ),
        )
        .order_by("-is_identical", "full_name", "id")
    )
