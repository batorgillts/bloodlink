"""Data Access for US-03: keep database queries and transactions in one place."""

from contextlib import contextmanager

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from accounts.models import User
from config.search import filter_text

from .models import Donation, DonationAppointment, DonationIntervalRule, Donor


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


def search_donors(*, name=None, email=None, blood_type=None, search=None, limit=None):
    queryset = active_donors().select_related("user")
    queryset = filter_text(queryset, search, ["full_name", "user__email"])
    if name:
        queryset = queryset.filter(full_name__icontains=name)
    if email:
        queryset = queryset.filter(user__email__icontains=email)
    if blood_type:
        queryset = queryset.filter(blood_type=blood_type)
    queryset = queryset.order_by("full_name", "id")
    return queryset[:limit] if limit is not None else queryset


def interval_rules():
    return list(DonationIntervalRule.objects.order_by("id"))


def donations_for(donor_id):
    return list(
        Donation.objects.filter(donor_id=donor_id)
        .select_related("recorded_by")
        .prefetch_related("blood_units")
        .order_by("-donation_date", "-id")
    )


def active_donors():
    """Search/matching must use active profiles; history lookups must not."""
    return Donor.objects.filter(
        status=Donor.Status.ACTIVE, user__is_active=True, user__role=User.Role.DONOR
    )


def locked_donation(donor_id, donation_id):
    return Donation.objects.select_for_update().filter(
        pk=donation_id, donor_id=donor_id
    ).first()


def remove_donation(donation):
    donation.delete()


def deactivate_donor(donor):
    donor.status = Donor.Status.DELETED
    donor.save(update_fields=["status"])
    donor.user.is_active = False
    donor.user.save(update_fields=["is_active"])
    cancel_uncompleted_appointments(donor.pk)


def mark_withdrawn(donor):
    """US-05: keep the donor row and its donations, and stop sign-in."""
    donor.status = Donor.Status.WITHDRAWN
    donor.save(update_fields=["status"])
    donor.user.is_active = False
    donor.user.save(update_fields=["is_active"])
    cancel_uncompleted_appointments(donor.pk)


@contextmanager
def locked_donor(donor_id):
    """US-09: use the same User -> Donor lock order as deletion and withdrawal."""
    donor = find_donor(donor_id)
    if donor is None:
        yield None
        return
    with locked_contact(donor.user_id) as current:
        yield current


def donation_dates(donor_id, donation_type, exclude_id=None):
    return list(
        Donation.objects.filter(donor_id=donor_id, donation_type_id=donation_type)
        .exclude(pk=exclude_id)
        .order_by("donation_date")
        .values_list("donation_date", flat=True)
    )


def create_donation(**fields):
    return Donation.objects.create(**fields)


def appointments_for(donor_id):
    return DonationAppointment.objects.filter(donor_id=donor_id).select_related(
        "donation_type", "unit"
    )


def find_appointment(donor_id, appointment_id, *, lock=False):
    records = appointments_for(donor_id)
    if lock:
        records = records.select_for_update(of=("self",))
    return records.filter(pk=appointment_id).first()


def appointment_rule(code):
    return DonationIntervalRule.objects.filter(donation_type=code).first()


def future_appointments(donor_id, now, *, exclude_id=None):
    return appointments_for(donor_id).filter(
        Q(status=DonationAppointment.Status.SCHEDULED, scheduled_at__gte=now)
        | Q(status=DonationAppointment.Status.IN_PROGRESS)
    ).exclude(pk=exclude_id)


def create_appointment(**fields):
    return DonationAppointment.objects.create(**fields)


def save_appointment(appointment, fields):
    for name, value in fields.items():
        setattr(appointment, name, value)
    appointment.save(update_fields=[*fields, "updated_at"])
    return appointment


def cancel_uncompleted_appointments(donor_id):
    """Account withdrawal/deactivation cancels every unfinished booking."""
    now = timezone.now()
    appointments_for(donor_id).filter(status__in=[
        DonationAppointment.Status.SCHEDULED, DonationAppointment.Status.IN_PROGRESS,
    ]).update(
        status=DonationAppointment.Status.CANCELLED, cancelled_at=now, updated_at=now,
        cancellation_reason=DonationAppointment.CancellationReason.ACCOUNT_INACTIVE,
    )


def search_appointments(*, search=None, donation_type=None, blood_type=None, status=None):
    records = DonationAppointment.objects.select_related(
        "donation_type", "donor__user", "unit"
    )
    records = filter_text(records, search, ["donor__full_name", "donor__user__email"])
    if donation_type:
        records = records.filter(donation_type=donation_type)
    if blood_type:
        records = records.filter(donor__blood_type=blood_type)
    if status:
        records = records.filter(status=status)
    return records


def appointment_donor_id(appointment_id):
    return DonationAppointment.objects.filter(pk=appointment_id).values_list(
        "donor_id", flat=True
    ).first()
