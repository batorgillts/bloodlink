from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from inventory.models import BloodUnit, ShelfLifeRule

from .models import Donation, DonationAppointment, DonationIntervalRule, Donor

URL = "/api/appointments/"
BANK_ZONE = ZoneInfo("America/New_York")


class CoordinatorAppointmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.coordinator = User.objects.create_user(
            "appointments-coordinator@example.com", "TestPassword123", role=User.Role.COORDINATOR
        )
        cls.user = User.objects.create_user("anna.chen+donor@example.com", "TestPassword123")
        cls.other = User.objects.create_user("joanna.chen@example.com", "TestPassword123")
        cls.donor = Donor.objects.create(
            user=cls.user,
            full_name="Anna Marie Chen",
            date_of_birth=date(1995, 1, 1),
            blood_type="A+",
            phone="2025550100",
        )
        cls.other_donor = Donor.objects.create(
            user=cls.other,
            full_name="Joanna Chen",
            date_of_birth=date(1994, 1, 1),
            blood_type="O-",
            phone="2025550101",
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.coordinator)
        self.now = datetime(2026, 11, 26, 17, 0, tzinfo=timezone.utc)
        clock = patch("django.utils.timezone.now", return_value=self.now)
        self.clock = clock.start()
        self.addCleanup(clock.stop)

    def appointment(self, donor=None, code="whole_blood", when=None, **extra):
        return DonationAppointment.objects.create(
            donor=donor or self.donor,
            donation_type=DonationIntervalRule.objects.get(donation_type=code),
            scheduled_at=when or self.now + timedelta(days=1),
            **extra,
        )

    def recordable(self, code="whole_blood"):
        appointment = self.appointment(code=code, when=self.now)
        self.assertEqual(self.start(appointment).status_code, 200)
        return appointment

    def start(self, appointment):
        return self.client.post(f"{URL}{appointment.pk}/start/", {}, format="json")

    def record(self, appointment, **overrides):
        data = {
            "unit_code": "APPT-001",
            "volume_ml": 450,
            "component": "RBC",
            "collected_date": "2026-11-26",
            "collected_time": "12:00",
        }
        data.update(overrides)
        return self.client.post(f"{URL}{appointment.pk}/record/", data, format="json")

    def listed_ids(self, **filters):
        response = self.client.get(URL, filters)
        self.assertEqual(response.status_code, 200)
        return {row["id"] for row in response.data["appointments"]}

    def test_list_has_donor_identity_donation_options_and_bank_timezone(self):
        appointment = self.appointment()
        other = self.appointment(donor=self.other_donor)
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["timezone"], "America/New_York")
        self.assertTrue(response.data["as_of"])
        self.assertEqual({row["id"] for row in response.data["appointments"]},
                         {appointment.pk, other.pk})
        row = next(item for item in response.data["appointments"] if item["id"] == appointment.pk)
        self.assertEqual(row["donor"], {
            "id": self.donor.pk, "full_name": self.donor.full_name,
            "email": self.user.email, "blood_type": "A+",
        })
        self.assertEqual(row["donation_type"], "whole_blood")
        self.assertEqual(set(row["allowed_components"]), {"RBC", "PLASMA", "PLATELETS"})
        self.assertIn("can_record", row)
        self.assertTrue(row["can_cancel"])
        self.assertIsNone(row["donation_id"])
        self.assertIsNone(row["unit_id"])
        self.assertIn("unit_code", row)
        self.assertIn("cancellation_reason", row)
        options = {option["donation_type"]: option for option in response.data["donation_types"]}
        self.assertEqual(options["plasma"]["allowed_components"], ["PLASMA"])
        self.assertTrue(options["plasma"]["label"])

    def test_search_is_case_insensitive_partial_and_combines_words_across_fields(self):
        first = self.appointment()
        second = self.appointment(donor=self.other_donor)
        self.assertEqual(self.listed_ids(search="ANN"), {first.pk, second.pk})
        self.assertEqual(self.listed_ids(search="cHeN"), {first.pk, second.pk})
        self.assertEqual(self.listed_ids(search="anna.chen+"), {first.pk})
        self.assertEqual(self.listed_ids(search="  marIE  DONOR@  "), {first.pk})
        self.assertEqual(self.listed_ids(search="Marie joanna"), set())

    def test_search_blood_type_donation_type_and_status_combine_with_and(self):
        target = self.appointment()
        plasma = self.appointment(code="plasma", when=self.now + timedelta(days=2))
        other = self.appointment(donor=self.other_donor)
        cancelled = self.appointment(
            when=self.now + timedelta(days=3), status="cancelled", cancelled_at=self.now
        )
        self.assertEqual(self.listed_ids(blood_type="A+"), {target.pk, plasma.pk, cancelled.pk})
        self.assertEqual(self.listed_ids(donation_type="whole_blood"),
                         {target.pk, other.pk, cancelled.pk})
        self.assertEqual(self.listed_ids(status="cancelled"), {cancelled.pk})
        self.assertEqual(self.listed_ids(
            search="chen donor@", blood_type="A+", donation_type="whole_blood", status="scheduled"
        ), {target.pk})
        self.assertEqual(self.listed_ids(
            search="chen donor@", blood_type="O-", donation_type="whole_blood", status="scheduled"
        ), set())

    def test_invalid_filter_values_are_rejected(self):
        for filters in ({"blood_type": "A"}, {"donation_type": "unknown"}, {"status": "unknown"}):
            with self.subTest(filters=filters):
                self.assertEqual(self.client.get(URL, filters).status_code, 400)

    def test_donor_and_anonymous_cannot_list_record_or_cancel(self):
        appointment = self.appointment()
        for user, status in ((self.user, 403), (None, 401)):
            with self.subTest(user=user):
                self.client.force_authenticate(user)
                self.assertEqual(self.client.get(URL).status_code, status)
                self.assertEqual(self.start(appointment).status_code, status)
                self.assertEqual(self.record(appointment).status_code, status)
                self.assertEqual(self.client.post(f"{URL}{appointment.pk}/cancel/", {
                    "confirm": True,
                }, format="json").status_code, status)
        self.assertEqual(Donation.objects.count(), 0)
        self.assertEqual(BloodUnit.objects.count(), 0)

    def test_record_uses_booking_identity_and_atomically_updates_inventory_and_eligibility(self):
        appointment = self.recordable()
        response = self.record(appointment, unit_code="  appt-001  ")
        self.assertEqual(response.status_code, 201)
        result = response.data["appointment"]
        self.assertEqual(result["status"], "completed")
        self.assertFalse(result["can_record"])
        self.assertFalse(result["can_cancel"])
        self.assertEqual(result["unit_code"], "APPT-001")
        self.assertEqual(response.data["unit"]["unit_code"], "APPT-001")
        donation = Donation.objects.get(pk=result["donation_id"])
        unit = BloodUnit.objects.get(pk=result["unit_id"])
        self.assertEqual(donation.donor_id, self.donor.pk)
        self.assertEqual(donation.donation_type_id, appointment.donation_type_id)
        self.assertEqual(donation.blood_type, "A+")
        self.assertEqual(donation.volume_ml, 450)
        self.assertEqual(donation.donation_date, date(2026, 11, 26))
        self.assertEqual(donation.recorded_by_id, self.coordinator.pk)
        self.assertEqual(unit.donation_id, donation.pk)
        self.assertEqual(unit.created_by_id, self.coordinator.pk)
        self.assertEqual(unit.blood_type, "A+")
        self.assertEqual(unit.component, "RBC")
        self.assertEqual(unit.collected_at, self.now)
        shelf_life = ShelfLifeRule.objects.get(component="RBC").shelf_life_days
        self.assertEqual(unit.expires_at, self.now + timedelta(days=shelf_life))
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "completed")
        self.client.force_authenticate(self.user)
        eligibility = self.client.get("/api/donors/me/eligibility/").json()
        self.assertEqual(len(eligibility["donations"]), 1)
        whole = next(row for row in eligibility["eligibility"]
                     if row["donation_type"] == "whole_blood")
        self.assertFalse(whole["eligible"])
        interval = DonationIntervalRule.objects.get(donation_type="whole_blood").min_interval_days
        self.assertEqual(whole["next_eligible_date"],
                         (date(2026, 11, 26) + timedelta(days=interval)).isoformat())
        donor_url = f"/api/donors/me/appointments/{appointment.pk}/"
        self.assertEqual(self.client.patch(donor_url, {
            "appointment_date": "2026-12-10",
        }, format="json").status_code, 409)
        self.assertEqual(self.client.post(f"{donor_url}cancel/", {
            "confirm": True,
        }, format="json").status_code, 409)

    def test_record_rejects_identity_status_and_source_overrides(self):
        appointment = self.recordable()
        for extra in (
            {"donor_id": self.other_donor.pk}, {"donation_type": "plasma"},
            {"blood_type": "O-"}, {"donation_id": 123}, {"status": "completed"},
        ):
            with self.subTest(extra=extra):
                self.assertEqual(self.record(appointment, **extra).status_code, 400)
        self.assertEqual(Donation.objects.count(), 0)
        self.assertEqual(BloodUnit.objects.count(), 0)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "in_progress")

    def test_component_must_match_booked_type_and_failed_record_leaves_no_donation(self):
        appointment = self.recordable(code="plasma")
        result = self.record(appointment, component="RBC")
        self.assertEqual(result.status_code, 400)
        self.assertEqual(Donation.objects.count(), 0)
        self.assertEqual(BloodUnit.objects.count(), 0)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "in_progress")

    def test_plasma_booking_records_its_configured_component_and_type(self):
        appointment = self.recordable(code="plasma")
        response = self.record(appointment, component="PLASMA", volume_ml=600)
        self.assertEqual(response.status_code, 201)
        result = response.data["appointment"]
        donation = Donation.objects.get(pk=result["donation_id"])
        unit = BloodUnit.objects.get(pk=result["unit_id"])
        self.assertEqual(donation.donation_type_id, "plasma")
        self.assertEqual(donation.volume_ml, 600)
        self.assertEqual(unit.component, "PLASMA")
        self.assertEqual(unit.donation_id, donation.pk)
        self.assertEqual(self.listed_ids(status="completed", donation_type="plasma"),
                         {appointment.pk})

    def test_record_revalidates_actual_donation_interval(self):
        appointment = self.recordable(code="plasma")
        Donation.objects.create(
            donor=self.donor, donation_type=appointment.donation_type,
            donation_date=date(2026, 11, 20), blood_type="A+", volume_ml=450,
            recorded_by=self.coordinator,
        )
        response = self.record(appointment, component="PLASMA")
        self.assertEqual(response.status_code, 400)
        self.assertIn("2026-12-18", str(response.data))
        self.assertEqual(Donation.objects.count(), 1)
        self.assertEqual(BloodUnit.objects.count(), 0)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "in_progress")

    def test_invalid_record_data_does_not_change_appointment(self):
        appointment = self.recordable()
        for fields in ({"unit_code": ""}, {"volume_ml": 0}, {"volume_ml": "1.5"},
                       {"collected_date": "2026-02-30"}, {"collected_time": "25:00"},
                       {"collected_date": "2026-11-27"}, {"collected_time": "12:01"}):
            with self.subTest(fields=fields):
                self.assertEqual(self.record(appointment, **fields).status_code, 400)
        self.assertEqual(Donation.objects.count(), 0)
        self.assertEqual(BloodUnit.objects.count(), 0)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "in_progress")

    def test_duplicate_unit_code_does_not_create_an_extra_donation(self):
        appointment = self.recordable()
        BloodUnit.objects.create(
            unit_code="APPT-001", blood_type="O-", component="RBC",
            collected_at=self.now, created_by=self.coordinator,
        )
        response = self.record(appointment, unit_code="appt-001")
        self.assertEqual(response.status_code, 409)
        self.assertEqual(Donation.objects.count(), 0)
        self.assertEqual(BloodUnit.objects.count(), 1)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "in_progress")

    def test_unexpected_unit_save_failure_rolls_back_the_whole_recording(self):
        appointment = self.recordable()
        with patch("inventory.models.BloodUnit.save",
                   side_effect=RuntimeError("unit write failed")):
            with self.assertRaises(RuntimeError):
                self.record(appointment)
        self.assertEqual(Donation.objects.count(), 0)
        self.assertEqual(BloodUnit.objects.count(), 0)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "in_progress")

    def test_completed_appointment_cannot_be_recorded_twice_or_cancelled(self):
        appointment = self.recordable()
        first = self.record(appointment)
        self.assertEqual(first.status_code, 201)
        repeated = self.record(appointment, unit_code="APPT-002")
        self.assertEqual(repeated.status_code, 409)
        cancelled = self.client.post(f"{URL}{appointment.pk}/cancel/", {
            "confirm": True,
        }, format="json")
        self.assertEqual(cancelled.status_code, 409)
        self.assertEqual(self.start(appointment).status_code, 409)
        self.assertEqual(Donation.objects.count(), 1)
        self.assertEqual(BloodUnit.objects.count(), 1)

    def test_coordinator_cancel_requires_confirmation_and_keeps_the_booking_history(self):
        appointment = self.appointment()
        url = f"{URL}{appointment.pk}/cancel/"
        for body in ({}, {"confirm": False}, {"confirm": "true"},
                     {"confirm": True, "donor_id": self.other_donor.pk}):
            with self.subTest(body=body):
                self.assertEqual(self.client.post(url, body, format="json").status_code, 400)
        cancelled = self.client.post(url, {"confirm": True}, format="json")
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.data["status"], "cancelled")
        self.assertFalse(cancelled.data["can_cancel"])
        self.assertFalse(cancelled.data["can_record"])
        self.assertTrue(cancelled.data["cancellation_reason"])
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "cancelled")
        self.assertIsNotNone(appointment.cancelled_at)
        self.assertEqual(DonationAppointment.objects.count(), 1)
        self.assertEqual(self.listed_ids(status="cancelled"), {appointment.pk})
        self.assertEqual(Donation.objects.count(), 0)
        self.assertEqual(BloodUnit.objects.count(), 0)

    def test_manual_cancellation_cannot_be_recorded_as_a_donation(self):
        appointment = self.recordable()
        self.assertEqual(self.client.post(f"{URL}{appointment.pk}/cancel/", {
            "confirm": True,
        }, format="json").status_code, 200)
        self.assertEqual(self.record(appointment).status_code, 409)
        self.assertEqual(Donation.objects.count(), 0)
        self.assertEqual(BloodUnit.objects.count(), 0)

    def test_unknown_appointment_operations_return_not_found(self):
        appointment = self.appointment()
        appointment.pk += 999
        self.assertEqual(self.start(appointment).status_code, 404)
        self.assertEqual(self.record(appointment).status_code, 404)
        self.assertEqual(self.client.post(f"{URL}{appointment.pk}/cancel/", {
            "confirm": True,
        }, format="json").status_code, 404)

    def test_start_at_scheduled_time_is_allowed_and_is_idempotent_after_time_passes(self):
        appointment = self.appointment(when=self.now)
        started = self.start(appointment)
        self.assertEqual(started.status_code, 200)
        self.assertEqual(started.data["status"], "in_progress")
        self.assertTrue(started.data["can_record"])
        self.assertTrue(started.data["can_cancel"])
        started_at = started.data["started_at"]
        self.clock.return_value = self.now + timedelta(hours=2)
        listed = self.client.get(URL)
        row = next(item for item in listed.data["appointments"] if item["id"] == appointment.pk)
        self.assertEqual(row["status"], "in_progress")
        self.assertEqual(row["started_at"], started_at)
        resumed = self.start(appointment)
        self.assertEqual(resumed.status_code, 200)
        self.assertEqual(resumed.data["started_at"], started_at)
        self.assertEqual(Donation.objects.count(), 0)
        self.assertEqual(BloodUnit.objects.count(), 0)

    def test_scheduled_booking_requires_start_before_recording(self):
        appointment = self.appointment(when=self.now)
        self.assertEqual(self.record(appointment).status_code, 409)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "scheduled")
        self.assertEqual(Donation.objects.count(), 0)
        self.assertEqual(BloodUnit.objects.count(), 0)

    def test_past_scheduled_bookings_stay_actionable_and_reads_do_not_change_them(self):
        appointment = self.appointment(when=self.now)
        self.assertEqual(self.client.get(URL).data["appointments"][0]["status"], "scheduled")
        self.clock.return_value = self.now + timedelta(days=1)
        result = self.client.get(URL)
        row = next(item for item in result.data["appointments"] if item["id"] == appointment.pk)
        self.assertEqual(row["status"], "scheduled")
        self.assertEqual(row["cancellation_reason"], "")
        self.assertTrue(row["can_record"])
        self.assertTrue(row["can_cancel"])
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "scheduled")
        self.assertIsNone(appointment.cancelled_at)
        self.assertEqual(Donation.objects.count(), 0)

    def test_past_scheduled_booking_can_be_started_and_recorded(self):
        appointment = self.appointment(when=self.now - timedelta(days=1))
        self.assertEqual(self.start(appointment).status_code, 200)
        response = self.record(appointment)
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["appointment"]["status"], "completed")
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "completed")
        self.assertIsNone(appointment.cancelled_at)
        self.assertEqual(Donation.objects.count(), 1)
        self.assertEqual(BloodUnit.objects.count(), 1)

    def test_past_scheduled_booking_can_be_cancelled_by_the_coordinator(self):
        appointment = self.appointment(when=self.now - timedelta(days=1))
        response = self.client.post(f"{URL}{appointment.pk}/cancel/", {
            "confirm": True,
        }, format="json")
        self.assertEqual(response.status_code, 200)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "cancelled")
        self.assertEqual(appointment.cancellation_reason, "coordinator")
        self.assertEqual(Donation.objects.count(), 0)
        self.assertEqual(BloodUnit.objects.count(), 0)

    def test_failed_record_does_not_cancel_a_past_scheduled_booking(self):
        appointment = self.appointment(when=self.now - timedelta(days=1))
        self.assertEqual(self.record(appointment).status_code, 409)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "scheduled")
        self.assertIsNone(appointment.cancelled_at)
        self.assertEqual(Donation.objects.count(), 0)
        self.assertEqual(BloodUnit.objects.count(), 0)

    def test_donor_cannot_modify_or_cancel_a_booking_already_in_progress(self):
        appointment = self.recordable()
        self.client.force_authenticate(self.user)
        url = f"/api/donors/me/appointments/{appointment.pk}/"
        self.assertEqual(self.client.patch(url, {
            "appointment_date": "2026-12-10",
        }, format="json").status_code, 409)
        self.assertEqual(self.client.post(f"{url}cancel/", {
            "confirm": True,
        }, format="json").status_code, 409)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "in_progress")

    def test_withdrawal_cancels_in_progress_booking_after_appointment_time(self):
        appointment = self.recordable()
        self.clock.return_value = self.now + timedelta(hours=1)
        self.client.force_authenticate(self.user)
        response = self.client.post("/api/donors/me/withdraw/", {"confirm": True}, format="json")
        self.assertEqual(response.status_code, 200)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "cancelled")
        self.assertEqual(appointment.cancellation_reason, "account_inactive")
        self.assertEqual(DonationAppointment.objects.count(), 1)
        self.assertEqual(Donation.objects.count(), 0)

    def test_donor_deactivation_cancels_in_progress_booking_after_appointment_time(self):
        appointment = self.recordable()
        self.clock.return_value = self.now + timedelta(hours=1)
        response = self.client.delete(f"/api/donors/{self.donor.pk}/", {
            "confirm": True,
        }, format="json")
        self.assertEqual(response.status_code, 200)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "cancelled")
        self.assertEqual(appointment.cancellation_reason, "account_inactive")
        self.assertEqual(DonationAppointment.objects.count(), 1)
        self.assertEqual(Donation.objects.count(), 0)
