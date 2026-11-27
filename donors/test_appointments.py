from datetime import date, datetime, timedelta, timezone
from unittest.mock import patch
from zoneinfo import ZoneInfo

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User

from .models import Donation, DonationAppointment, DonationIntervalRule, Donor

URL = "/api/donors/me/appointments/"
BANK_ZONE = ZoneInfo("America/New_York")


class DonorAppointmentTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("appointments@example.com", "TestPassword123")
        cls.other = User.objects.create_user("other-appointments@example.com", "TestPassword123")
        cls.coordinator = User.objects.create_user(
            "appointment-coordinator@example.com", "TestPassword123", role=User.Role.COORDINATOR
        )
        cls.donor = Donor.objects.create(
            user=cls.user,
            full_name="Appointment Donor",
            date_of_birth=date(1995, 1, 1),
            blood_type="A+",
            phone="2025550100",
        )
        cls.other_donor = Donor.objects.create(
            user=cls.other,
            full_name="Another Donor",
            date_of_birth=date(1994, 1, 1),
            blood_type="O-",
            phone="2025550101",
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)
        self.now = datetime(2026, 11, 26, 17, 0, tzinfo=timezone.utc)
        clock = patch("donors.appointments.timezone.now", return_value=self.now)
        self.clock = clock.start()
        self.addCleanup(clock.stop)

    def create(self, **overrides):
        body = {
            "donation_type": "whole_blood",
            "appointment_date": "2026-12-10",
            "appointment_time": "09:00",
        }
        body.update(overrides)
        return self.client.post(URL, body, format="json")

    def stored_appointment(self, donor=None, code="whole_blood", when=None, **extra):
        return DonationAppointment.objects.create(
            donor=donor or self.donor,
            donation_type=DonationIntervalRule.objects.get(donation_type=code),
            scheduled_at=when or datetime(2026, 12, 10, 9, 0, tzinfo=BANK_ZONE),
            **extra,
        )

    def donation(self, code="plasma", on=date(2026, 11, 20)):
        return Donation.objects.create(
            donor=self.donor,
            donation_type=DonationIntervalRule.objects.get(donation_type=code),
            donation_date=on,
            blood_type=self.donor.blood_type,
            volume_ml=450,
            recorded_by=self.coordinator,
        )

    def test_create_and_list_return_own_appointment_in_bank_time(self):
        self.stored_appointment(donor=self.other_donor)
        created = self.create()
        self.assertEqual(created.status_code, 201)
        body = created.json()
        self.assertEqual(body["donation_type"], "whole_blood")
        self.assertTrue(body["donation_type_label"])
        self.assertEqual(body["appointment_date"], "2026-12-10")
        self.assertEqual(body["appointment_time"], "09:00")
        self.assertEqual(body["timezone"], "America/New_York")
        self.assertEqual(body["status"], "scheduled")
        self.assertTrue(body["can_modify"])
        self.assertIsNone(body["cancelled_at"])
        self.assertTrue(body["created_at"])
        self.assertTrue(body["updated_at"])
        stored = DonationAppointment.objects.get(pk=body["id"])
        self.assertEqual(stored.donor_id, self.donor.pk)
        self.assertEqual(stored.scheduled_at, datetime(2026, 12, 10, 14, 0, tzinfo=timezone.utc))
        listed = self.client.get(URL)
        self.assertEqual(listed.status_code, 200)
        self.assertEqual([item["id"] for item in listed.json()], [stored.pk])
        detail = self.client.get(f"{URL}{stored.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["id"], stored.pk)

    def test_future_eligible_date_can_be_booked_even_when_not_eligible_today(self):
        self.donation()
        row = next(
            item for item in self.client.get("/api/donors/me/eligibility/").json()["eligibility"]
            if item["donation_type"] == "plasma"
        )
        self.assertFalse(row["eligible"])
        self.assertEqual(row["next_eligible_date"], "2026-12-18")
        early = self.create(donation_type="plasma", appointment_date="2026-12-17")
        self.assertEqual(early.status_code, 400)
        self.assertIn("2026-12-18", str(early.data))
        self.assertEqual(DonationAppointment.objects.count(), 0)
        boundary = self.create(donation_type="plasma", appointment_date="2026-12-18")
        self.assertEqual(boundary.status_code, 201)

    def test_interval_changes_are_used_at_booking_time(self):
        self.donation()
        rule = DonationIntervalRule.objects.get(donation_type="plasma")
        rule.min_interval_days = 35
        rule.save(update_fields=["min_interval_days"])
        response = self.create(donation_type="plasma", appointment_date="2026-12-18")
        self.assertEqual(response.status_code, 400)
        self.assertIn("2026-12-25", str(response.data))

    def test_past_or_current_time_is_rejected_but_later_today_is_allowed(self):
        for on, at in (("2026-11-25", "14:00"), ("2026-11-26", "11:59"),
                       ("2026-11-26", "12:00")):
            with self.subTest(on=on, at=at):
                response = self.create(appointment_date=on, appointment_time=at)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(DonationAppointment.objects.count(), 0)
        response = self.create(appointment_date="2026-11-26", appointment_time="12:01")
        self.assertEqual(response.status_code, 201)

    def test_bank_date_around_utc_midnight_does_not_reject_later_same_local_day(self):
        self.clock.return_value = datetime(2026, 11, 27, 4, 30, tzinfo=timezone.utc)
        response = self.create(appointment_date="2026-11-26", appointment_time="23:45")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["appointment_date"], "2026-11-26")
        stored = DonationAppointment.objects.get(pk=response.data["id"])
        self.assertEqual(stored.scheduled_at, datetime(2026, 11, 27, 4, 45, tzinfo=timezone.utc))

    def test_nonexistent_and_ambiguous_daylight_saving_times_are_rejected(self):
        for on, at in (("2027-03-14", "02:30"), ("2027-11-07", "01:30")):
            with self.subTest(on=on):
                response = self.create(appointment_date=on, appointment_time=at)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(DonationAppointment.objects.count(), 0)
        response = self.create(appointment_date="2027-03-14", appointment_time="03:30")
        self.assertEqual(response.status_code, 201)
        stored = DonationAppointment.objects.get(pk=response.data["id"])
        self.assertEqual(stored.scheduled_at, datetime(2027, 3, 14, 7, 30, tzinfo=timezone.utc))

    def test_invalid_and_unknown_fields_are_rejected(self):
        cases = (
            {"donation_type": "unknown"},
            {"appointment_date": "2026-02-30"},
            {"appointment_time": "25:00"},
            {"donor": self.other_donor.pk},
            {"donor_id": self.other_donor.pk},
            {"status": "cancelled"},
            {"scheduled_at": "2026-12-10T10:00:00Z"},
        )
        for fields in cases:
            with self.subTest(fields=fields):
                response = self.create(**fields)
                self.assertEqual(response.status_code, 400)
        self.assertEqual(self.client.post(URL, {}, format="json").status_code, 400)
        self.assertEqual(DonationAppointment.objects.count(), 0)

    def test_same_time_is_rejected_across_donation_types(self):
        self.assertEqual(self.create().status_code, 201)
        duplicate = self.create(donation_type="plasma")
        self.assertEqual(duplicate.status_code, 400)
        self.assertEqual(DonationAppointment.objects.count(), 1)

    def test_scheduled_same_type_appointments_require_interval_in_both_directions(self):
        self.stored_appointment(code="platelets", when=datetime(2026, 12, 20, 9, tzinfo=BANK_ZONE))
        for on in ("2026-12-14", "2026-12-26"):
            with self.subTest(on=on):
                response = self.create(donation_type="platelets", appointment_date=on)
                self.assertEqual(response.status_code, 400)
        boundary = self.create(donation_type="platelets", appointment_date="2026-12-13")
        self.assertEqual(boundary.status_code, 201)

    def test_different_types_at_different_times_can_be_booked(self):
        self.assertEqual(self.create().status_code, 201)
        response = self.create(donation_type="platelets", appointment_time="10:00")
        self.assertEqual(response.status_code, 201)

    def test_past_appointment_does_not_count_as_a_recorded_donation(self):
        self.stored_appointment(when=self.now - timedelta(days=1))
        response = self.create(appointment_date="2026-11-27")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(Donation.objects.count(), 0)

    def test_modify_rechecks_eligibility_and_excludes_its_own_record(self):
        appointment = self.stored_appointment()
        url = f"{URL}{appointment.pk}/"
        unchanged = self.client.patch(url, {"appointment_time": "09:00"}, format="json")
        self.assertEqual(unchanged.status_code, 200)
        self.donation()
        invalid = self.client.patch(url, {"donation_type": "plasma"}, format="json")
        self.assertEqual(invalid.status_code, 400)
        appointment.refresh_from_db()
        self.assertEqual(appointment.donation_type_id, "whole_blood")
        self.assertEqual(appointment.scheduled_at.day, 10)
        valid = self.client.patch(url, {
            "donation_type": "plasma", "appointment_date": "2026-12-18",
            "appointment_time": "10:15",
        }, format="json")
        self.assertEqual(valid.status_code, 200)
        appointment.refresh_from_db()
        self.assertEqual(appointment.donation_type_id, "plasma")
        self.assertEqual(valid.data["appointment_date"], "2026-12-18")
        self.assertEqual(valid.data["appointment_time"], "10:15")

    def test_modify_rechecks_future_time_conflicts_and_rejects_empty_patch(self):
        first = self.stored_appointment(code="platelets")
        self.stored_appointment(code="platelets", when=datetime(2026, 12, 20, 9, tzinfo=BANK_ZONE))
        url = f"{URL}{first.pk}/"
        for fields in ({"appointment_date": "2026-12-19"},
                       {"appointment_date": "2026-11-25"}, {}, {"status": "cancelled"}):
            with self.subTest(fields=fields):
                self.assertEqual(self.client.patch(url, fields, format="json").status_code, 400)
        first.refresh_from_db()
        self.assertEqual(first.scheduled_at.astimezone(BANK_ZONE).date(), date(2026, 12, 10))

    def test_cancel_retains_history_is_idempotent_and_releases_the_time(self):
        appointment = self.stored_appointment()
        url = f"{URL}{appointment.pk}/cancel/"
        cancelled = self.client.post(url, {"confirm": True}, format="json")
        self.assertEqual(cancelled.status_code, 200)
        self.assertEqual(cancelled.data["status"], "cancelled")
        self.assertFalse(cancelled.data["can_modify"])
        self.assertTrue(cancelled.data["cancelled_at"])
        repeated = self.client.post(url, {"confirm": True}, format="json")
        self.assertEqual(repeated.status_code, 200)
        self.assertEqual(repeated.data["cancelled_at"], cancelled.data["cancelled_at"])
        self.assertEqual(DonationAppointment.objects.count(), 1)
        self.assertEqual(self.create().status_code, 201)
        self.assertEqual(len(self.client.get(URL).data), 2)
        edited = self.client.patch(f"{URL}{appointment.pk}/", {
            "appointment_time": "10:00",
        }, format="json")
        self.assertEqual(edited.status_code, 409)

    def test_cancel_requires_explicit_boolean_confirmation(self):
        appointment = self.stored_appointment()
        for body in ({}, {"confirm": False}, {"confirm": "true"},
                     {"confirm": True, "status": "cancelled"}):
            with self.subTest(body=body):
                result = self.client.post(f"{URL}{appointment.pk}/cancel/", body, format="json")
                self.assertEqual(result.status_code, 400)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "scheduled")

    def test_past_appointments_are_read_only_for_the_donor_and_do_not_change_on_read(self):
        appointment = self.stored_appointment(when=self.now - timedelta(minutes=1))
        listed = self.client.get(URL)
        self.assertEqual(listed.data[0]["status"], "scheduled")
        detail = self.client.get(f"{URL}{appointment.pk}/")
        self.assertEqual(detail.status_code, 200)
        self.assertFalse(detail.data["can_modify"])
        self.assertEqual(detail.data["status"], "scheduled")
        self.assertEqual(detail.data["cancellation_reason"], "")
        self.assertEqual(self.client.patch(f"{URL}{appointment.pk}/", {
            "appointment_date": "2026-12-10",
        }, format="json").status_code, 409)
        self.assertEqual(self.client.post(f"{URL}{appointment.pk}/cancel/", {
            "confirm": True,
        }, format="json").status_code, 409)
        appointment.refresh_from_db()
        self.assertEqual(appointment.status, "scheduled")
        self.assertIsNone(appointment.cancelled_at)
        self.assertEqual(Donation.objects.count(), 0)

    def test_creating_modifying_and_cancelling_does_not_change_actual_eligibility(self):
        self.donation()
        before = self.client.get("/api/donors/me/eligibility/").json()
        created = self.create(donation_type="plasma", appointment_date="2026-12-18")
        self.assertEqual(created.status_code, 201)
        appointment_id = created.data["id"]
        self.assertEqual(self.client.patch(f"{URL}{appointment_id}/", {
            "appointment_time": "11:00",
        }, format="json").status_code, 200)
        self.assertEqual(self.client.get("/api/donors/me/eligibility/").json(), before)
        self.assertEqual(self.client.post(f"{URL}{appointment_id}/cancel/", {
            "confirm": True,
        }, format="json").status_code, 200)
        self.assertEqual(self.client.get("/api/donors/me/eligibility/").json(), before)
        self.assertEqual(Donation.objects.count(), 1)

    def test_other_donors_appointments_are_not_accessible(self):
        foreign = self.stored_appointment(donor=self.other_donor)
        self.assertEqual(self.client.get(URL).json(), [])
        for appointment_id in (foreign.pk, foreign.pk + 999):
            with self.subTest(appointment_id=appointment_id):
                url = f"{URL}{appointment_id}/"
                self.assertEqual(self.client.get(url).status_code, 404)
                self.assertEqual(self.client.patch(url, {
                    "appointment_time": "11:00",
                }, format="json").status_code, 404)
                self.assertEqual(self.client.post(f"{url}cancel/", {
                    "confirm": True,
                }, format="json").status_code, 404)
        foreign.refresh_from_db()
        self.assertEqual(foreign.status, "scheduled")

    def test_coordinators_and_anonymous_users_cannot_use_donor_appointment_endpoints(self):
        appointment = self.stored_appointment()
        for user, expected in ((self.coordinator, 403), (None, 401)):
            self.client.force_authenticate(user)
            with self.subTest(user=user):
                self.assertEqual(self.client.get(URL).status_code, expected)
                self.assertEqual(self.create().status_code, expected)
                self.assertEqual(self.client.get(f"{URL}{appointment.pk}/").status_code, expected)
                self.assertEqual(self.client.patch(f"{URL}{appointment.pk}/", {
                    "appointment_time": "10:00",
                }, format="json").status_code, expected)
                self.assertEqual(self.client.post(f"{URL}{appointment.pk}/cancel/", {
                    "confirm": True,
                }, format="json").status_code, expected)

    def test_inactive_withdrawn_and_deleted_donors_are_denied(self):
        appointment = self.stored_appointment()
        cases = ((False, "active"), (True, "withdrawn"), (True, "deleted"))
        for active, status in cases:
            with self.subTest(active=active, status=status):
                self.user.is_active = active
                self.user.save(update_fields=["is_active"])
                self.donor.status = status
                self.donor.save(update_fields=["status"])
                self.assertEqual(self.client.get(URL).status_code, 403)
                self.assertEqual(self.create().status_code, 403)
                self.assertEqual(self.client.patch(f"{URL}{appointment.pk}/", {
                    "appointment_time": "10:00",
                }, format="json").status_code, 403)
                self.assertEqual(self.client.post(f"{URL}{appointment.pk}/cancel/", {
                    "confirm": True,
                }, format="json").status_code, 403)

    def test_withdrawal_cancels_own_unfinished_appointments_and_keeps_history(self):
        upcoming = self.stored_appointment()
        past = self.stored_appointment(when=self.now - timedelta(days=1))
        other = self.stored_appointment(donor=self.other_donor)
        self.donation()
        response = self.client.post("/api/donors/me/withdraw/", {"confirm": True}, format="json")
        self.assertEqual(response.status_code, 200)
        upcoming.refresh_from_db()
        past.refresh_from_db()
        other.refresh_from_db()
        self.assertEqual(upcoming.status, "cancelled")
        self.assertIsNotNone(upcoming.cancelled_at)
        self.assertEqual(past.status, "cancelled")
        self.assertEqual(past.cancellation_reason, "account_inactive")
        self.assertIsNotNone(past.cancelled_at)
        self.assertEqual(other.status, "scheduled")
        self.assertEqual(DonationAppointment.objects.count(), 3)
        self.assertEqual(Donation.objects.count(), 1)

    def test_donor_deletion_cancels_unfinished_appointments_without_removing_history(self):
        upcoming = self.stored_appointment()
        past = self.stored_appointment(when=self.now - timedelta(days=1))
        self.client.force_authenticate(self.coordinator)
        response = self.client.delete(
            f"/api/donors/{self.donor.pk}/", {"confirm": True}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        upcoming.refresh_from_db()
        past.refresh_from_db()
        self.assertEqual(upcoming.status, "cancelled")
        self.assertIsNotNone(upcoming.cancelled_at)
        self.assertEqual(past.status, "cancelled")
        self.assertEqual(past.cancellation_reason, "account_inactive")
        self.assertIsNotNone(past.cancelled_at)
        self.assertEqual(DonationAppointment.objects.count(), 2)
