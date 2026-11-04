"""Database operations for US-11 blood request records."""

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
