"""Contact update rules for Donor & Donation Management (US-03)."""

from django.db import IntegrityError
from rest_framework.exceptions import NotFound, PermissionDenied

from accounts.models import User
from config.exceptions import Conflict

from . import repository
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
