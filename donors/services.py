"""Contact update rules for Donor & Donation Management (US-03)."""

from django.db import IntegrityError
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied

from accounts.models import User
from config.exceptions import Conflict

from . import calculator, repository
from .models import Donor


def ensure_active_donor(donor):
    if (
        not donor.user.is_active
        or donor.user.role != User.Role.DONOR
        or donor.status != Donor.Status.ACTIVE
    ):
        raise PermissionDenied("This donor account is not active.")


def get_own_contact(user_id, donor_id=None):
    donor = repository.find_contact(user_id)
    if donor is None:
        raise NotFound("Donor profile not found.")
    # Check against the caller's profile; never fetch another donor's record.
    # A non-owned ID gets 403 whether or not that ID exists.
    if donor_id is not None and donor_id != donor.pk:
        raise PermissionDenied("You can only view or update your own contact information.")
    ensure_active_donor(donor)
    return donor


def duplicate_email():
    return Conflict({"email": ["An account with this email is already registered."]})


def update_contact(donor, changes):
    user_id = donor.user_id
    email = changes.get("email")
    try:
        with repository.locked_contact(user_id) as current:
            ensure_active_donor(current)
            if email is not None and repository.email_in_use(email, user_id):
                raise duplicate_email()
            repository.save_contact(current, changes)
            return current
    except IntegrityError:
        # The database is the final guard if another account claimed the email
        # after the initial check. Check outside the rolled-back transaction.
        if email is not None and repository.email_in_use(email, user_id):
            raise duplicate_email() from None
        raise


NO_HISTORY_MESSAGE = "No previous donations are recorded."
OWN_RECORDS_ONLY = "You can only view your own donation history and eligibility."


def bank_today():
    # Settings use America/New_York. "Today" follows the blood bank, not UTC.
    return timezone.localdate()


def get_eligibility(user, donor_id=None):
    today = bank_today()
    if user.role == User.Role.COORDINATOR:
        return _coordinator_eligibility(donor_id, today)
    if user.role != User.Role.DONOR:
        raise PermissionDenied("You cannot view donation eligibility.")
    return _donor_eligibility(user.pk, donor_id, today)


def _coordinator_eligibility(donor_id, today):
    # Coordinators have no donor profile. /me/ belongs to the signed-in donor.
    if donor_id is None:
        raise PermissionDenied("Coordinators must look up a donor by id.")
    donor = repository.find_donor(donor_id)
    if donor is None:
        raise NotFound("Donor profile not found.")
    return _eligibility_payload(donor, today)


def _donor_eligibility(user_id, donor_id, today):
    donor = repository.find_contact(user_id)
    if donor is None:
        raise NotFound("Donor profile not found.")
    # Deny a non-owned id whether or not that id exists, and do not look it up.
    if donor_id is not None and donor_id != donor.pk:
        raise PermissionDenied(OWN_RECORDS_ONLY)
    ensure_active_donor(donor)
    return _eligibility_payload(donor, today)


def _eligibility_payload(donor, today):
    donations = repository.donations_for(donor.pk)
    rules = repository.interval_rules()
    calculated = calculator.calculate_eligibility(
        rules=[(rule.donation_type, rule.min_interval_days) for rule in rules],
        donations=[(donation.donation_type_id, donation.donation_date) for donation in donations],
        today=today,
    )
    recorded = bool(donations)
    return {
        "donor_id": donor.pk,
        "as_of": today.isoformat(),
        "no_donation_history": not recorded,
        "message": None if recorded else NO_HISTORY_MESSAGE,
        "donations": [_donation_row(donation) for donation in donations],
        "eligibility": [_eligibility_row(row) for row in calculated],
    }


def _donation_row(donation):
    return {
        "donation_id": donation.pk,
        "donation_type": donation.donation_type_id,
        "donation_date": donation.donation_date.isoformat(),
        "blood_type": donation.blood_type,
        "volume_ml": donation.volume_ml,
    }


def _eligibility_row(row):
    last = row["last_donation_date"]
    return {
        "donation_type": row["donation_type"],
        "label": row["donation_type"].replace("_", " ").title(),
        "min_interval_days": row["min_interval_days"],
        "last_donation_date": None if last is None else last.isoformat(),
        "next_eligible_date": row["next_eligible_date"].isoformat(),
        "eligible": row["eligible"],
    }


def ensure_coordinator(user):
    if not user.is_active or user.role != User.Role.COORDINATOR:
        raise PermissionDenied("Only active coordinators can delete records.")


def delete_donation(user, donor_id, donation_id):
    ensure_coordinator(user)
    donor = repository.find_donor(donor_id)
    if donor is None:
        raise NotFound("Donor profile not found.")
    # Same User -> Donor lock order as contact updates and donor deletion.
    with repository.locked_contact(donor.user_id) as current:
        donation = repository.locked_donation(current.pk, donation_id)
        if donation is None:
            raise NotFound("Donation entry not found for this donor.")
        repository.remove_donation(donation)
        # Calculate inside the transaction: failure rolls the deletion back.
        return {
            "message": "Donation entry deleted successfully.",
            "deleted_donation_id": donation_id,
            "donor": _eligibility_payload(current, bank_today()),
        }


def delete_donor(user, donor_id):
    ensure_coordinator(user)
    donor = repository.find_donor(donor_id)
    if donor is None:
        raise NotFound("Donor profile not found.")
    with repository.locked_contact(donor.user_id) as current:
        # Repeated confirmed requests are safe and return the same final state.
        repository.deactivate_donor(current)
        return {
            "message": "Donor record deleted. Donation history retained.",
            "donor_id": current.pk,
            "status": current.status,
        }
