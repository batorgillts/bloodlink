"""Donor self-service booking rules, using the bank's configured donation intervals."""

from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from django.utils import timezone
from rest_framework.exceptions import NotFound, ValidationError

from config.exceptions import Conflict

from . import calculator, repository, services
from .models import DonationAppointment

BANK_TIMEZONE = ZoneInfo("America/New_York")


def local_appointment_time(day, time):
    """Reject clock-change gaps/ambiguities rather than silently shifting a booking."""
    naive = datetime.combine(day, time)
    candidates = {
        naive.replace(tzinfo=BANK_TIMEZONE, fold=fold).astimezone(UTC)
        for fold in (0, 1)
        if naive.replace(tzinfo=BANK_TIMEZONE, fold=fold)
        .astimezone(UTC).astimezone(BANK_TIMEZONE).replace(tzinfo=None) == naive
    }
    if len(candidates) != 1:
        raise ValidationError({"appointment_time": [
            "This time is unavailable because the clocks change in America/New_York. "
            "Choose another time."
        ]})
    return candidates.pop()


def appointment_payload(appointment, now=None):
    now = now or timezone.now()
    local = appointment.scheduled_at.astimezone(BANK_TIMEZONE)
    return {
        "id": appointment.pk,
        "donation_type": appointment.donation_type_id,
        "donation_type_label": appointment.donation_type_id.replace("_", " ").title(),
        "appointment_date": local.date().isoformat(),
        "appointment_time": local.strftime("%H:%M"),
        "scheduled_at": local.isoformat(),
        "timezone": str(BANK_TIMEZONE),
        "status": appointment.status,
        "can_modify": (
            appointment.status == DonationAppointment.Status.SCHEDULED
            and appointment.scheduled_at > now
        ),
        "created_at": appointment.created_at.isoformat(),
        "updated_at": appointment.updated_at.isoformat(),
        "cancelled_at": appointment.cancelled_at.isoformat() if appointment.cancelled_at else None,
        "cancellation_reason": appointment.cancellation_reason,
        "completed_at": appointment.completed_at.isoformat() if appointment.completed_at else None,
        "started_at": appointment.started_at.isoformat() if appointment.started_at else None,
        "donation_id": appointment.donation_id,
        "unit_id": appointment.unit_id,
        "unit_code": appointment.unit.unit_code if appointment.unit_id else None,
    }


def list_appointments(user_id):
    donor = services.get_own_contact(user_id)
    now = timezone.now()
    return [appointment_payload(row, now) for row in repository.appointments_for(donor.pk)]


def own_appointment(donor_id, appointment_id, *, lock=False):
    appointment = repository.find_appointment(donor_id, appointment_id, lock=lock)
    if appointment is None:
        raise NotFound("Appointment not found.")
    return appointment


def get_appointment(user_id, appointment_id):
    donor = services.get_own_contact(user_id)
    return appointment_payload(own_appointment(donor.pk, appointment_id))


def ensure_modifiable(appointment, now):
    if appointment.status == DonationAppointment.Status.COMPLETED:
        raise Conflict("Completed appointments cannot be changed or cancelled.")
    if appointment.status == DonationAppointment.Status.IN_PROGRESS:
        raise Conflict("This appointment is being handled by the blood bank and cannot be changed.")
    if appointment.status != DonationAppointment.Status.SCHEDULED:
        raise Conflict("Cancelled appointments cannot be changed. Book a new appointment.")
    if appointment.scheduled_at <= now:
        raise Conflict("Past appointments cannot be changed or cancelled.")


def validate_booking(donor, rule, scheduled_at, now, *, exclude_id=None):
    if scheduled_at <= now:
        raise ValidationError({"appointment_time": ["Choose a future appointment date and time."]})
    day = scheduled_at.astimezone(BANK_TIMEZONE).date()
    dates = repository.donation_dates(donor.pk, rule.donation_type)
    eligibility = calculator.calculate_eligibility(
        rules=[(rule.donation_type, rule.min_interval_days)],
        donations=[(rule.donation_type, donated_on) for donated_on in dates],
        today=now.astimezone(BANK_TIMEZONE).date(),
    )[0]
    earliest = eligibility["next_eligible_date"]
    if day < earliest:
        label = rule.donation_type.replace("_", " ")
        raise ValidationError({"appointment_date": [
            f"You can book {label} on or after {earliest.isoformat()} "
            "under the current donation interval rules."
        ]})
    for other in repository.future_appointments(donor.pk, now, exclude_id=exclude_id):
        if other.scheduled_at == scheduled_at:
            raise ValidationError({"appointment_time": [
                "You already have an appointment at this time. Edit that appointment instead."
            ]})
        other_day = other.scheduled_at.astimezone(BANK_TIMEZONE).date()
        if (
            other.donation_type_id == rule.donation_type
            and abs((day - other_day).days) < rule.min_interval_days
        ):
            raise ValidationError({"appointment_date": [
                f"Keep at least {rule.min_interval_days} days between appointments of this type. "
                f"Your other appointment is on {other_day.isoformat()}."
            ]})


def save_booking(user_id, data, *, appointment_id=None):
    # The same User -> Donor lock order as recording a donation and withdrawing.
    services.get_own_contact(user_id)
    def save(donor, now):
        services.ensure_active_donor(donor)
        current = None
        if appointment_id is not None:
            current = own_appointment(donor.pk, appointment_id, lock=True)
            ensure_modifiable(current, now)
        previous = current.scheduled_at.astimezone(BANK_TIMEZONE) if current else None
        code = data["donation_type"].donation_type if "donation_type" in data else (
            current.donation_type_id if current else None
        )
        rule = repository.appointment_rule(code)
        if rule is None:
            raise ValidationError({"donation_type": ["Choose an available donation type."]})
        day = data.get("appointment_date", previous.date() if previous else None)
        time = data.get("appointment_time", previous.time() if previous else None)
        scheduled_at = local_appointment_time(day, time)
        validate_booking(donor, rule, scheduled_at, now, exclude_id=appointment_id)
        fields = {"donation_type": rule, "scheduled_at": scheduled_at}
        saved = (
            repository.save_appointment(current, fields)
            if current else repository.create_appointment(donor=donor, **fields)
        )
        return appointment_payload(saved, now)

    return run_locked_appointment_action(user_id, save)


def cancel_booking(user_id, appointment_id):
    services.get_own_contact(user_id)

    def cancel(donor, now):
        services.ensure_active_donor(donor)
        appointment = own_appointment(donor.pk, appointment_id, lock=True)
        if appointment.status == DonationAppointment.Status.CANCELLED:
            return appointment_payload(appointment, now)
        ensure_modifiable(appointment, now)
        repository.save_appointment(appointment, {
            "status": DonationAppointment.Status.CANCELLED,
            "cancelled_at": now,
            "cancellation_reason": DonationAppointment.CancellationReason.DONOR,
            "cancelled_by": donor.user,
        })
        return appointment_payload(appointment, now)

    return run_locked_appointment_action(user_id, cancel)


def run_locked_appointment_action(user_id, action):
    """Serialize donor/appointment writes and roll back any failed action together."""
    with repository.locked_contact(user_id) as donor:
        return action(donor, timezone.now())
