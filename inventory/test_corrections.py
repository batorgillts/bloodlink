from datetime import date, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from donors.models import Donation, DonationIntervalRule, Donor

from .models import BloodUnit


class UnitCorrectionTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.coordinator = User.objects.create_user(
            "coordinator@example.com", "abc123456", role=User.Role.COORDINATOR
        )
        self.user = User.objects.create_user("donor@example.com", "abc123456")
        self.donor = Donor.objects.create(
            user=self.user, full_name="Demo Donor", date_of_birth=date(1998, 5, 12),
            blood_type="A+", phone="2025550100",
        )
        self.client.force_authenticate(self.coordinator)
        self.rule = DonationIntervalRule.objects.get(donation_type="whole_blood")
        self.collected = timezone.now() - timedelta(days=5)
        self.donation = Donation.objects.create(
            donor=self.donor, donation_type=self.rule,
            donation_date=timezone.localdate(self.collected), blood_type="A+",
            volume_ml=450, recorded_by=self.coordinator,
        )
        self.unit = BloodUnit.objects.create(
            unit_code="CORRECTION", donation=self.donation, component="RBC",
            blood_type="A+", collected_at=self.collected, created_by=self.coordinator,
        )
        self.url = f"/api/units/{self.unit.pk}/"

    def correct(self, data):
        return self.client.patch(self.url, data, format="json")

    def whole(self):
        payload = self.client.get(f"/api/donors/{self.donor.pk}/").data
        return next(e for e in payload["eligibility"] if e["donation_type"] == "whole_blood")

    def test_demo_donor_record_today_becomes_not_yet_eligible(self):
        self.unit.delete()
        self.donation.delete()
        collected = timezone.now() - timedelta(minutes=2)
        response = self.client.post("/api/units/", {
            "unit_code": "TODAY", "donor_id": self.donor.pk, "donation_type": "whole_blood",
            "volume_ml": 450, "component": "PLASMA", "blood_type": "A+",
            "collected_at": collected.isoformat(),
        }, format="json")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(response.data["component"], "PLASMA")
        self.assertEqual(response.data["source_donation"]["donation_type"], "whole_blood")
        self.client.force_authenticate(self.user)
        data = self.client.get("/api/donors/me/eligibility/").data
        self.assertEqual(len(data["donations"]), 1)
        self.assertEqual(data["donations"][0]["units"][0]["component"], "PLASMA")
        whole = next(e for e in data["eligibility"] if e["donation_type"] == "whole_blood")
        self.assertFalse(whole["eligible"])
        self.assertEqual(whole["next_eligible_date"],
                         (timezone.localdate(collected) + timedelta(days=56)).isoformat())

    def test_year_1111_is_rejected_for_new_donation_and_unit(self):
        data = {"donation_date": "1111-11-11", "donation_type": "plasma",
                "blood_type": "A+", "volume_ml": 450}
        response = self.client.post(f"/api/donors/{self.donor.pk}/donations/", data, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("date of birth", str(response.data))
        data.pop("donation_date")
        response = self.client.post("/api/units/", {**data, "donor_id": self.donor.pk,
            "unit_code": "INVALID-YEAR", "component": "PLASMA",
            "collected_at": "1111-11-11T10:00:00-05:00"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Donation.objects.count(), 1)
        self.assertEqual(BloodUnit.objects.count(), 1)

    def test_time_and_component_edit_recomputes_expiry_without_changing_method(self):
        new_time = self.collected - timedelta(hours=1)
        response = self.correct({"component": "PLASMA", "collected_at": new_time.isoformat()})
        self.assertEqual(response.status_code, 200, response.data)
        self.unit.refresh_from_db()
        self.donation.refresh_from_db()
        self.assertEqual(self.unit.component, "PLASMA")
        self.assertEqual(self.unit.expires_at, timezone.localtime(new_time) + timedelta(days=365))
        self.assertEqual(self.donation.donation_type_id, "whole_blood")
        self.assertEqual(Donation.objects.count(), 1)

    def test_calendar_date_edit_updates_siblings_and_eligibility_once(self):
        sibling = BloodUnit.objects.create(
            unit_code="SIBLING", donation=self.donation, component="PLASMA", blood_type="A+",
            collected_at=self.collected + timedelta(minutes=10),
        )
        new_time = self.collected + timedelta(days=2)
        response = self.correct({"collected_at": new_time.isoformat()})
        self.assertEqual(response.status_code, 200, response.data)
        self.donation.refresh_from_db()
        sibling.refresh_from_db()
        self.assertEqual(self.donation.donation_date, timezone.localdate(new_time))
        self.assertEqual(sibling.collected_at, new_time + timedelta(minutes=10))
        self.assertEqual(self.whole()["next_eligible_date"],
                         (timezone.localdate(new_time) + timedelta(days=56)).isoformat())
        self.assertEqual(Donation.objects.count(), 1)

    def test_explicit_method_correction_updates_rule_and_component(self):
        response = self.correct({"donation_type": "plasma", "component": "PLASMA"})
        self.assertEqual(response.status_code, 200, response.data)
        self.donation.refresh_from_db()
        self.assertEqual(self.donation.donation_type_id, "plasma")
        data = self.client.get(f"/api/donors/{self.donor.pk}/").data
        row = next(e for e in data["eligibility"] if e["donation_type"] == "plasma")
        self.assertEqual(row["next_eligible_date"],
                         (self.donation.donation_date + timedelta(days=28)).isoformat())

    def test_incompatible_method_and_component_rejected_on_create_and_edit(self):
        response = self.correct({"donation_type": "plasma"})
        self.assertEqual(response.status_code, 400)
        self.donation.refresh_from_db()
        self.assertEqual(self.donation.donation_type_id, "whole_blood")
        response = self.client.post("/api/units/", {
            "unit_code": "BAD-COMPONENT", "donor_id": self.donor.pk,
            "donation_type": "platelets", "volume_ml": 200, "blood_type": "A+",
            "component": "RBC", "collected_at": self.collected.isoformat(),
        }, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Donation.objects.count(), 1)

    def test_interval_collision_future_and_before_birth_dates_are_rejected(self):
        Donation.objects.create(
            donor=self.donor, donation_type=self.rule,
            donation_date=timezone.localdate(self.collected) - timedelta(days=100),
            blood_type="A+", volume_ml=450, recorded_by=self.coordinator,
        )
        for value in ((self.collected - timedelta(days=99)).isoformat(),
                      (timezone.now() + timedelta(days=1)).isoformat(),
                      "1111-11-11T10:00:00-05:00"):
            self.assertEqual(self.correct({"collected_at": value}).status_code, 400)
        self.unit.refresh_from_db()
        self.assertEqual(self.unit.collected_at, self.collected)

    def test_reserved_or_discarded_unit_and_shared_source_are_protected(self):
        sibling = BloodUnit.objects.create(
            unit_code="LOCKED", donation=self.donation, component="PLASMA", blood_type="A+",
            collected_at=self.collected, status="reserved",
        )
        self.assertEqual(self.correct({"collected_at":
            (self.collected + timedelta(days=1)).isoformat()}).status_code, 409)
        self.url = f"/api/units/{sibling.pk}/"
        self.assertEqual(self.correct({"component": "RBC"}).status_code, 409)
        sibling.status = "discarded"
        sibling.discard_reason = "damaged"
        sibling.save()
        self.assertEqual(self.correct({"component": "RBC"}).status_code, 409)

    def test_unknown_fields_and_non_coordinator_are_rejected(self):
        for data in ({}, {"donor_id": self.donor.pk}, {"expires_at": "2027-01-01"},
                     {"unit_code": "OTHER"}, {"status": "available"}):
            self.assertEqual(self.correct(data).status_code, 400)
        for user, expected in ((self.user, 403), (None, 401)):
            self.client.force_authenticate(user)
            self.assertEqual(self.correct({"component": "PLASMA"}).status_code, expected)

    def test_old_invalid_test_date_can_be_corrected_without_duplicate_donation(self):
        old = timezone.datetime(1111, 11, 11, 10, tzinfo=timezone.get_current_timezone())
        self.unit.collected_at = old
        self.unit.expires_at = None
        self.unit.save()
        self.donation.donation_date = date(1111, 11, 11)
        self.donation.save()
        self.assertTrue(self.whole()["eligible"])
        response = self.correct({"collected_at": self.collected.isoformat()})
        self.assertEqual(response.status_code, 200, response.data)
        self.assertFalse(self.whole()["eligible"])
        self.assertEqual(Donation.objects.count(), 1)

    def test_save_failure_rolls_back_source_date_and_sibling_changes(self):
        before = self.donation.donation_date
        with patch("inventory.models.BloodUnit.save", side_effect=RuntimeError("write failed")):
            with self.assertRaises(RuntimeError):
                self.correct({"collected_at": (self.collected + timedelta(days=1)).isoformat()})
        self.donation.refresh_from_db()
        self.assertEqual(self.donation.donation_date, before)
