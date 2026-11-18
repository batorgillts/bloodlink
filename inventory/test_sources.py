from datetime import timedelta
from unittest.mock import patch

from django.db import IntegrityError
from django.db.models.deletion import ProtectedError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from donors.models import Donation, DonationIntervalRule, Donor

from .models import BloodUnit


class UnitSourceTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.coordinator = User.objects.create_user(
            "source-coord@example.com", "Password123", role=User.Role.COORDINATOR
        )
        self.user = User.objects.create_user("source-donor@example.com", "Password123")
        self.donor = Donor.objects.create(
            user=self.user, full_name="Source Donor", date_of_birth="1990-01-01",
            blood_type="A+", phone="2125550100",
        )
        self.client.force_authenticate(self.coordinator)
        self.collected = timezone.now() - timedelta(minutes=5)
        self.payload = {
            "unit_code": "SOURCE-1", "blood_type": "A+", "component": "RBC",
            "collected_at": self.collected.isoformat(), "donor_id": self.donor.pk,
            "donation_type": "whole_blood", "volume_ml": 450,
        }

    def post(self, **overrides):
        return self.client.post("/api/units/", {**self.payload, **overrides}, format="json")

    def existing(self, donation):
        return {k: v for k, v in {**self.payload, "donation_id": donation.pk}.items()
                if k not in ("donation_type", "volume_ml")}

    def test_new_donation_updates_own_history_and_eligibility(self):
        response = self.post()
        self.assertEqual(response.status_code, 201, response.data)
        unit = BloodUnit.objects.get()
        self.assertEqual(unit.donation.donor, self.donor)
        self.assertEqual(unit.donation.recorded_by, self.coordinator)
        self.assertEqual(response.data["source_donation"]["donor_id"], self.donor.pk)
        self.client.force_authenticate(self.user)
        history = self.client.get("/api/donors/me/eligibility/").data
        self.assertEqual(len(history["donations"]), 1)
        self.assertEqual(history["donations"][0]["unit_codes"], ["SOURCE-1"])
        row = next(e for e in history["eligibility"] if e["donation_type"] == "whole_blood")
        rule = DonationIntervalRule.objects.get(donation_type="whole_blood")
        expected = timezone.localdate(self.collected) + timedelta(days=rule.min_interval_days)
        self.assertEqual(row["next_eligible_date"], expected.isoformat())
        self.assertFalse(row["eligible"])

    def test_multiple_processed_units_reuse_one_donation(self):
        self.assertEqual(self.post().status_code, 201)
        donation = Donation.objects.get()
        self.payload = self.existing(donation)
        before = self.client.get(f"/api/donors/{self.donor.pk}/").data["eligibility"]
        response = self.post(unit_code="SOURCE-2", component="PLASMA")
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Donation.objects.count(), 1)
        self.assertEqual(donation.blood_units.count(), 2)
        self.assertEqual(
            self.client.get(f"/api/donors/{self.donor.pk}/").data["eligibility"], before
        )

    def test_missing_or_ambiguous_source_rejected(self):
        self.assertEqual(self.post().status_code, 201)
        self.payload = self.existing(Donation.objects.get())
        self.assertEqual(self.post(unit_code="OTHER", volume_ml=450).status_code, 400)
        self.payload.pop("donation_id")
        self.assertEqual(self.post(unit_code="OTHER").status_code, 400)
        self.payload.pop("donor_id")
        self.assertEqual(self.post(unit_code="OTHER").status_code, 400)
        self.assertEqual(BloodUnit.objects.count(), 1)

    def test_wrong_donor_blood_type_and_collection_date_rejected(self):
        self.post()
        self.payload = self.existing(Donation.objects.get())
        other = Donor.objects.create(
            user=User.objects.create_user("other-source@example.com", "Password123"),
            full_name="Other", date_of_birth="1990-01-01", blood_type="A+", phone="2125550101",
        )
        bad_values = [
            {"donor_id": other.pk}, {"donation_id": 999999}, {"blood_type": "O+"},
            {"collected_at": (self.collected - timedelta(days=1)).isoformat()},
        ]
        for values in bad_values:
            with self.subTest(values=values):
                self.assertEqual(self.post(unit_code="OTHER", **values).status_code, 400)
        self.assertEqual(BloodUnit.objects.count(), 1)

    def test_invalid_new_donation_does_not_create_inventory(self):
        for values in ({"volume_ml": 0}, {"blood_type": "O+"}, {"donation_type": "unknown"},
                       {"collected_at": (timezone.now() + timedelta(days=1)).isoformat()}):
            with self.subTest(values=values):
                self.assertEqual(self.post(**values).status_code, 400)
        self.assertFalse(Donation.objects.exists())
        self.assertFalse(BloodUnit.objects.exists())

    def test_eligibility_failure_rolls_back_unit(self):
        self.post()
        response = self.post(unit_code="SECOND-DONATION")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(Donation.objects.count(), 1)
        self.assertEqual(BloodUnit.objects.count(), 1)

    def test_unit_save_failure_rolls_back_new_donation(self):
        with patch("inventory.services.BloodUnit.objects.create", side_effect=IntegrityError):
            self.assertEqual(self.post().status_code, 409)
        self.assertFalse(Donation.objects.exists())
        self.assertFalse(BloodUnit.objects.exists())

    def test_duplicate_submission_does_not_add_history(self):
        self.assertEqual(self.post().status_code, 201)
        self.assertEqual(self.post().status_code, 409)
        self.assertEqual(Donation.objects.count(), 1)

    def test_linked_donation_cannot_be_deleted_even_after_discard(self):
        self.post()
        donation = Donation.objects.get()
        url = f"/api/donors/{self.donor.pk}/donations/{donation.pk}/"
        for discarded in (False, True):
            if discarded:
                unit = BloodUnit.objects.get()
                self.assertEqual(self.client.post(
                    f"/api/units/{unit.pk}/discard/", {"reason": "damaged"}, format="json"
                ).status_code, 200)
            self.assertEqual(self.client.delete(url, {"confirm": True}, format="json").status_code,
                             409)
            with self.assertRaises(ProtectedError):
                donation.delete()
        self.assertTrue(Donation.objects.exists())

    def test_donor_and_anonymous_users_cannot_record_units_or_donations(self):
        for user, expected in ((self.user, 403), (None, 401)):
            self.client.force_authenticate(user)
            self.assertEqual(self.post().status_code, expected)
            self.assertEqual(self.client.post(
                f"/api/donors/{self.donor.pk}/donations/", {}, format="json"
            ).status_code, expected)
        self.assertFalse(Donation.objects.exists())

    def test_inactive_donor_cannot_be_source(self):
        self.donor.status = Donor.Status.WITHDRAWN
        self.donor.save()
        self.assertEqual(self.post().status_code, 403)
        self.assertFalse(Donation.objects.exists())

    def test_legacy_units_remain_readable_without_fabricated_source(self):
        unit = BloodUnit.objects.create(
            unit_code="LEGACY", blood_type="A+", component="RBC", collected_at=self.collected
        )
        response = self.client.get(f"/api/units/{unit.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertIsNone(response.data["source_donation"])
        self.assertIsNone(response.data["donation_id"])

    def test_inventory_search_matches_code_name_email_and_combines_filters(self):
        self.assertEqual(self.post().status_code, 201)
        self.payload = self.existing(Donation.objects.get())
        self.assertEqual(self.post(unit_code="SOURCE-2", component="PLASMA").status_code, 201)
        for search in ("SOURCE-1", "source", "DoNoR", "source-donor@", "donor source",
                       " SOURCE-1   example.com "):
            with self.subTest(search=search):
                response = self.client.get("/api/units/", {
                    "search": search, "component": "RBC", "blood_type": "A+",
                    "status": "available",
                })
                self.assertEqual(response.status_code, 200)
                self.assertEqual([u["unit_code"] for u in response.data], ["SOURCE-1"])
        for params in ({"search": "source", "blood_type": "O-"},
                       {"search": "source", "status": "expired"},
                       {"search": "unmatched"}, {"search": "%"}, {"search": "_"}):
            self.assertEqual(self.client.get("/api/units/", params).data, [])

    def test_inventory_search_preserves_unknown_sources_and_retained_history(self):
        self.post()
        BloodUnit.objects.create(
            unit_code="LEGACY-SEARCH", blood_type="A+", component="RBC",
            collected_at=self.collected,
        )
        response = self.client.get("/api/units/", {"search": "legacy"})
        self.assertEqual([u["unit_code"] for u in response.data], ["LEGACY-SEARCH"])
        self.assertEqual(len(self.client.get("/api/units/", {"search": "  "}).data), 2)
        self.donor.status = Donor.Status.DELETED
        self.donor.save()
        response = self.client.get("/api/units/", {"search": "source-donor@"})
        self.assertEqual([u["unit_code"] for u in response.data], ["SOURCE-1"])
        self.assertEqual(self.client.get("/api/units/", {"search": "x" * 255}).status_code, 400)
        self.client.force_authenticate(self.user)
        self.assertEqual(self.client.get("/api/units/", {"search": "source"}).status_code, 403)
