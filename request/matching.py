"""Read-only matching for US-13, US-14 and US-15 using component-specific rules."""

from rest_framework.exceptions import NotFound, ValidationError

from config.choices import Component

from . import repository


def match_blood_request(request_id):
    blood_request = repository.find_matching_request(request_id)
    if blood_request is None:
        raise NotFound("Blood request not found.")
    if blood_request.component not in (
        Component.RED_BLOOD_CELLS,
        Component.PLASMA,
        Component.PLATELETS,
    ):
        raise ValidationError("Matching is not implemented for this component yet.")
    return repository.compatible_units(blood_request)
