"""Contact update rules for Donor & Donation Management (US-03)."""

from django.db import IntegrityError
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from accounts.models import User
from accounts.services import create_donor_account
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


def search_donor_records(filters):
    return repository.search_donors(**filters)


def get_donor_record(donor_id):
    donor = repository.find_donor(donor_id)
    if donor is None:
        raise NotFound("Donor record not found.")
    return donor


def create_walk_in_donor(data):
    """US-08: create the same User/Donor pair as self-registration, without tokens."""
    _user, donor = create_donor_account(**data)
    return donor


def update_donor_record(donor, changes):
    email = changes.get("email")
    try:
        with repository.locked_contact(donor.user_id) as current:
            if email is not None and repository.email_in_use(email, current.user_id):
                raise duplicate_email()
            repository.save_donor_record(current, changes)
            return current
    except IntegrityError:
        if email is not None and repository.email_in_use(email, donor.user_id):
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


INACTIVE_DONOR = "Donations can only be recorded for an active donor."

def record_donation(donor_id, data, coordinator):
    """US-09 implementation"""

    rule = data["donation_type"]
    donation_date = data["donation_date"]

    with repository.locked_donor(donor_id) as donor:
        if donor is None:
            raise NotFound("Donor record not found.")
        if donor.status != Donor.Status.ACTIVE or not donor.user.is_active:
            raise Conflict(INACTIVE_DONOR)
        if data["blood_type"] != donor.blood_type:
            raise ValidationError(
                {"blood_type": [f"Does not match the donor's blood type ({donor.blood_type})."]}
            )
        _check_interval(donor.pk, rule, donation_date)

        donation = repository.create_donation(
            donor=donor,
            donation_type=rule,
            donation_date=donation_date,
            blood_type=data["blood_type"],
            volume_ml=data["volume_ml"],
            recorded_by=coordinator,
        )

    return {"donation": _donation_row(donation), **_eligibility_payload(donor, bank_today())}


def _check_interval(donor_id, rule, donation_date):
    dates = repository.donation_dates(donor_id, rule.donation_type)
    # Same formula as US-04
    on_that_day = calculator.calculate_eligibility(
        rules=[(rule.donation_type, rule.min_interval_days)],
        donations=[(rule.donation_type, d) for d in dates if d <= donation_date],
        today=donation_date,
    )[0]
    if not on_that_day["eligible"]:
        raise ValidationError(
            {
                "donation_date": [
                    f"The donor is not eligible for {rule.donation_type} until "
                    f"{on_that_day['next_eligible_date'].isoformat()}."
                ]
            }
        )
    later = [d for d in dates if d > donation_date]
    if later and (later[0] - donation_date).days < rule.min_interval_days:
        raise ValidationError(
            {
                "donation_date": [
                    f"This date is within {rule.min_interval_days} days of the "
                    f"{rule.donation_type} donation already recorded on {later[0].isoformat()}."
                ]
            }
        )
