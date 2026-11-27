"""Coordinator appointment workflow, sharing inventory and donation validation."""

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError

from accounts.models import User
from config.exceptions import Conflict
from inventory.models import BloodUnit
from inventory.serializers import BloodUnitSerializer
from inventory.services import record_unit

from . import appointments, repository, services
from .models import DonationAppointment


def ensure_coordinator(user):
    if not user.is_active or user.role != User.Role.COORDINATOR:
        raise PermissionDenied("Only active coordinators can manage appointments.")


def coordinator_payload(appointment, now=None):
    now = now or timezone.now()
    active = appointment.status in (
        DonationAppointment.Status.SCHEDULED, DonationAppointment.Status.IN_PROGRESS
    )
    donor = appointment.donor
    return {
        **appointments.appointment_payload(appointment, now),
        "donor": {
            "id": donor.pk,
            "full_name": donor.full_name,
            "email": donor.user.email,
            "blood_type": donor.blood_type,
        },
        "allowed_components": appointment.donation_type.allowed_components,
        "can_record": active and donor.status == donor.Status.ACTIVE and donor.user.is_active,
        "can_cancel": active,
    }


def list_appointments(coordinator, filters):
    ensure_coordinator(coordinator)
    now = timezone.now()
    return {
        "appointments": [coordinator_payload(row, now)
                         for row in repository.search_appointments(**filters)],
        "donation_types": [
            {"donation_type": rule.donation_type,
             "label": rule.donation_type.replace("_", " ").title(),
             "allowed_components": rule.allowed_components}
            for rule in repository.interval_rules()
        ],
        "timezone": str(appointments.BANK_TIMEZONE),
        "as_of": now.isoformat(),
    }


def _perform(coordinator, appointment_id, action):
    ensure_coordinator(coordinator)
    donor_id = repository.appointment_donor_id(appointment_id)
    donor = repository.find_donor(donor_id) if donor_id else None
    if donor is None:
        raise NotFound("Appointment not found.")

    def locked_action(current_donor, now):
        appointment = appointments.own_appointment(current_donor.pk, appointment_id, lock=True)
        appointment.donor = current_donor
        return action(current_donor, appointment, now)

    return appointments.run_locked_appointment_action(donor.user_id, locked_action)


def start_appointment(coordinator, appointment_id):
    def start(donor, appointment, now):
        services.ensure_active_donor(donor)
        if appointment.status == DonationAppointment.Status.IN_PROGRESS:
            return coordinator_payload(appointment, now)
        if appointment.status != DonationAppointment.Status.SCHEDULED:
            raise Conflict("Only a scheduled appointment can be started.")
        repository.save_appointment(appointment, {
            "status": DonationAppointment.Status.IN_PROGRESS,
            "started_at": now,
            "started_by": coordinator,
        })
        return coordinator_payload(appointment, now)

    return _perform(coordinator, appointment_id, start)


def cancel_appointment(coordinator, appointment_id):
    def cancel(_donor, appointment, now):
        if appointment.status == DonationAppointment.Status.CANCELLED:
            return coordinator_payload(appointment, now)
        if appointment.status not in (
            DonationAppointment.Status.SCHEDULED, DonationAppointment.Status.IN_PROGRESS
        ):
            raise Conflict("Completed appointments cannot be cancelled.")
        repository.save_appointment(appointment, {
            "status": DonationAppointment.Status.CANCELLED,
            "cancelled_at": now,
            "cancelled_by": coordinator,
            "cancellation_reason": DonationAppointment.CancellationReason.COORDINATOR,
        })
        return coordinator_payload(appointment, now)

    return _perform(coordinator, appointment_id, cancel)


def record_appointment(coordinator, appointment_id, data):
    def record(donor, appointment, now):
        services.ensure_active_donor(donor)
        if appointment.status != DonationAppointment.Status.IN_PROGRESS:
            raise Conflict("Start this appointment before recording a blood unit.")
        try:
            collected_at = appointments.local_appointment_time(
                data["collected_date"], data["collected_time"]
            )
        except ValidationError as error:
            raise ValidationError({"collected_time": error.detail["appointment_time"]}) from error
        # Donor, blood type and donation type are derived from locked server records.
        # No donation_id is passed: every completion creates a new actual donation.
        unit_data = BloodUnitSerializer(data={
            "unit_code": data["unit_code"],
            "volume_ml": data["volume_ml"],
            "component": data["component"],
            "collected_at": collected_at,
            "donor_id": donor.pk,
            "blood_type": donor.blood_type,
            "donation_type": appointment.donation_type_id,
        })
        unit_data.is_valid(raise_exception=True)
        try:
            with transaction.atomic():
                unit = record_unit(unit_data.validated_data, coordinator)
        except IntegrityError:
            if BloodUnit.objects.filter(unit_code=unit_data.validated_data["unit_code"]).exists():
                raise Conflict("A blood unit with this code already exists.") from None
            raise
        repository.save_appointment(appointment, {
            "status": DonationAppointment.Status.COMPLETED,
            "completed_at": now,
            "donation": unit.donation,
            "unit": unit,
        })
        return {"appointment": coordinator_payload(appointment, now),
                "unit": BloodUnitSerializer(unit).data}

    return _perform(coordinator, appointment_id, record)
