"""Database access for blood requests and compatible inventory."""

from django.db.models import OuterRef, Subquery

from inventory.models import BloodUnit, CompatibilityRule

from .models import BloodRequest


def list_blood_requests():
    return BloodRequest.objects.select_related("logged_by").all()


def create_blood_request(*, logged_by, blood_type, component, quantity):
    return BloodRequest.objects.create(
        logged_by=logged_by,
        blood_type=blood_type,
        component=component,
        quantity=quantity,
    )


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
