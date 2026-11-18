from django.utils import timezone
from rest_framework.exceptions import NotFound

from config.choices import Component
from config.exceptions import Conflict
from donors.calculator import calculate_eligibility

from . import repository
from .models import BloodRequest

NO_DONORS_MESSAGE = "No eligible donors found."

# The donation a donor would give to supply each requested component.
COMPONENT_DONATION_TYPE = {
    Component.RED_BLOOD_CELLS: "whole_blood",
    Component.PLASMA: "plasma",
    Component.PLATELETS: "platelets",
}

OPEN_STATUSES = (BloodRequest.Status.PENDING, BloodRequest.Status.PARTIALLY_FULFILLED)


def suggest_donors(request_id, today=None):
    """Return (request, donation_type, [(donor, eligibility_row), ...])."""
    blood_request = repository.find_request(request_id)
    if blood_request is None:
        raise NotFound("Blood request not found.")
    if blood_request.status not in OPEN_STATUSES:
        raise Conflict(
            "Donor suggestions are only available for pending or partially fulfilled requests."
        )

    today = today or timezone.localdate()
    donation_type = COMPONENT_DONATION_TYPE[blood_request.component]
    rule = [(donation_type, repository.interval_days(donation_type))]

    suggestions = []
    for donor in repository.compatible_donors(blood_request, donation_type):
        history = [(donation_type, donor.last_of_type)] if donor.last_of_type else []
        [row] = calculate_eligibility(rules=rule, donations=history, today=today)
        # AC2: a donor whose next eligible date is in the future is left out.
        if row["eligible"]:
            suggestions.append((donor, row))
    return blood_request, donation_type, suggestions
