"""Data Access for US-03: keep database queries and transactions in one place."""

from contextlib import contextmanager

from django.db import transaction

from accounts.models import User

from .models import Donation, DonationIntervalRule, Donor


def find_contact(user_id):
    return Donor.objects.select_related("user").filter(user_id=user_id).first()


def email_in_use(email, user_id):
    return User.objects.filter(email__iexact=email).exclude(pk=user_id).exists()


@contextmanager
def locked_contact(user_id):
    # Both writes either succeed or roll back. Lock the account first, then its
    # profile, to serialize concurrent edits to the same donor on PostgreSQL.
    with transaction.atomic():
        user = User.objects.select_for_update().get(pk=user_id)
        donor = Donor.objects.select_for_update().get(user_id=user_id)
        donor.user = user
        yield donor


def save_contact(donor, changes):
    if "email" in changes:
        donor.user.email = changes["email"]
        donor.user.save(update_fields=["email"])
    if "phone" in changes:
        donor.phone = changes["phone"]
        donor.save(update_fields=["phone"])


def find_donor(donor_id):
    return Donor.objects.select_related("user").filter(pk=donor_id).first()


def interval_rules():
    return list(DonationIntervalRule.objects.order_by("id"))


def donations_for(donor_id):
    return list(Donation.objects.filter(donor_id=donor_id).order_by("-donation_date", "-id"))
