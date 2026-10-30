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
    # profile,to avoid concurrent edits
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


def save_donor_record(donor, changes):
    donor_fields = []
    if "email" in changes:
        donor.user.email = changes["email"]
        donor.user.save(update_fields=["email"])
    for field in ("full_name", "date_of_birth", "blood_type", "phone"):
        if field in changes:
            setattr(donor, field, changes[field])
            donor_fields.append(field)
    if donor_fields:
        donor.save(update_fields=donor_fields)


def find_donor(donor_id):
    return Donor.objects.select_related("user").filter(pk=donor_id).first()


def search_donors(*, name=None, email=None, blood_type=None):
    queryset = Donor.objects.select_related("user").filter(
        user__role=User.Role.DONOR,
        status=Donor.Status.ACTIVE,
    )
    if name:
        queryset = queryset.filter(full_name__icontains=name)
    if email:
        queryset = queryset.filter(user__email__icontains=email)
    if blood_type:
        queryset = queryset.filter(blood_type=blood_type)
    return queryset.order_by("full_name", "id")


def interval_rules():
    return list(DonationIntervalRule.objects.order_by("id"))


def donations_for(donor_id):
    return list(Donation.objects.filter(donor_id=donor_id).order_by("-donation_date", "-id"))



@contextmanager
def locked_donor(donor_id):
    """US-09: lock one donor row so two coordinators recording a donation for the same
    donor at the same moment are checked one after the other (PostgreSQL row lock)."""
    with transaction.atomic():
        yield Donor.objects.select_for_update().select_related("user").filter(pk=donor_id).first()


def donation_dates(donor_id, donation_type):
    return list(
        Donation.objects.filter(donor_id=donor_id, donation_type_id=donation_type)
        .order_by("donation_date")
        .values_list("donation_date", flat=True)
    )


def create_donation(**fields):
    return Donation.objects.create(**fields)
