"""Read-only matching rules for US-14.

US-13 red cells use the same read-only query. Compatibility lives in
CompatibilityRule, so each component keeps its own seeded rule set.
"""

from rest_framework.exceptions import NotFound, ValidationError

from config.choices import Component

from . import repository


def match_blood_request(request_id):
    blood_request = repository.find_matching_request(request_id)
    if blood_request is None:
        raise NotFound("Blood request not found.")
    # US-13: rank available RBC units from the seeded ABO/Rh rules.
    if blood_request.component == Component.RED_BLOOD_CELLS:
        return repository.compatible_units(blood_request)
    if blood_request.component != Component.PLASMA:
        raise ValidationError("Matching is not implemented for this component yet.")
    return repository.compatible_units(blood_request)
