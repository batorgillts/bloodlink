"""Read-only matching rules for US-14."""

from rest_framework.exceptions import NotFound, ValidationError

from config.choices import Component

from . import repository


def match_blood_request(request_id):
    blood_request = repository.find_matching_request(request_id)
    if blood_request is None:
        raise NotFound("Blood request not found.")
    if blood_request.component != Component.PLASMA:
        raise ValidationError("Matching is not implemented for this component yet.")
    return repository.compatible_units(blood_request)
