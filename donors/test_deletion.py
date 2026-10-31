from datetime import date
from unittest.mock import patch

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User

from . import repository, services
from .models import Donation, DonationIntervalRule, Donor

PASSWORD = "TestPassword123"


class DeletionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.coordinator = User.objects.create_user(
            "delete-coord@example.com", PASSWORD, role=User.Role.COORDINATOR
        )
        cls.user = User.objects.create_user("delete-donor@example.com", PASSWORD)
        cls.donor = Donor.objects.create(
            user=cls.user, full_name="Deletion Demo", date_of_birth=date(1990, 1, 1),
            blood_type="O+", phone="2125550100",
        )
        cls.other_user = User.objects.create_user("delete-other@example.com", PASSWORD)
        cls.other = Donor.objects.create(
            user=cls.other_user, full_name="Other Demo", date_of_birth=date(1990, 1, 1),
            blood_type="A+", phone="2125550101",
        )
        rule = DonationIntervalRule.objects.get(donation_type="whole_blood")
        cls.old = Donation.objects.create(
            donor=cls.donor, donation_type=rule, donation_date=date(2026, 1, 1),
            blood_type="O+", volume_ml=450, recorded_by=cls.coordinator,
        )
        cls.latest = Donation.objects.create(
            donor=cls.donor, donation_type=rule, donation_date=date(2026, 10, 20),
            blood_type="O+", volume_ml=450, recorded_by=cls.coordinator,
        )

    def setUp(self):
        self.client = APIClient()
        self.authenticate(self.coordinator)
        self.donor_url = f"/api/donors/{self.donor.pk}/"
        self.entry_url = f"{self.donor_url}donations/{self.latest.pk}/"
        self.history_url = f"{self.donor_url}eligibility/"
        clock = patch("donors.services.bank_today", return_value=date(2026, 10, 29))
        clock.start()
        self.addCleanup(clock.stop)

    def authenticate(self, user):
        token = str(RefreshToken.for_user(user).access_token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def remove(self, url, data=None):
        return self.client.delete(url, {"confirm": True} if data is None else data, format="json")

    def whole(self, payload):
        return next(r for r in payload["eligibility"] if r["donation_type"] == "whole_blood")

    def assert_unchanged(self):
        self.donor.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(self.donor.status, Donor.Status.ACTIVE)
        self.assertTrue(self.user.is_active)
        self.assertTrue(Donation.objects.filter(pk=self.latest.pk).exists())

    def test_delete_latest_recalculates_and_history_no_longer_contains_entry(self):
        self.assertFalse(self.whole(self.client.get(self.history_url).json())["eligible"])
        response = self.remove(self.entry_url)
        self.assertEqual(response.status_code, 200)
        self.assertIn("successfully", response.data["message"])
        self.assertEqual(response.data["deleted_donation_id"], self.latest.pk)
        updated = response.data["donor"]
        self.assertEqual(self.whole(updated)["next_eligible_date"], "2026-02-26")
        self.assertTrue(self.whole(updated)["eligible"])
        history = self.client.get(self.history_url).json()
        self.assertEqual(history, updated)
        self.assertEqual([d["donation_id"] for d in history["donations"]], [self.old.pk])

    def test_delete_older_entry_keeps_latest_eligibility(self):
        before = self.client.get(self.history_url).json()["eligibility"]
        response = self.remove(f"{self.donor_url}donations/{self.old.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["donor"]["eligibility"], before)

    def test_delete_final_entry_returns_no_history_and_eligible_today(self):
        self.remove(f"{self.donor_url}donations/{self.old.pk}/")
        response = self.remove(self.entry_url)
        payload = response.data["donor"]
        self.assertTrue(payload["no_donation_history"])
        self.assertEqual(payload["donations"], [])
        for row in payload["eligibility"]:
            self.assertTrue(row["eligible"])
            self.assertEqual(row["next_eligible_date"], "2026-10-29")

    def test_deletion_does_not_change_another_donation_type(self):
        platelet = Donation.objects.create(
            donor=self.donor,
            donation_type=DonationIntervalRule.objects.get(donation_type="platelets"),
            donation_date=date(2026, 10, 28), blood_type="O+", volume_ml=200,
            recorded_by=self.coordinator,
        )
        response = self.remove(self.entry_url)
        row = next(r for r in response.data["donor"]["eligibility"]
                   if r["donation_type"] == "platelets")
        self.assertEqual(row["next_eligible_date"], "2026-11-04")
        self.assertTrue(Donation.objects.filter(pk=platelet.pk).exists())

    def test_donor_deletion_retains_named_history_and_excludes_active_candidates(self):
        self.assertTrue(repository.active_donors().filter(pk=self.donor.pk).exists())
        history = self.client.get(self.history_url).json()["donations"]
        response = self.remove(self.donor_url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "deleted")
        self.donor.refresh_from_db()
        self.user.refresh_from_db()
        self.assertEqual(self.donor.full_name, "Deletion Demo")
        self.assertEqual(self.donor.status, Donor.Status.DELETED)
        self.assertFalse(self.user.is_active)
        self.assertFalse(repository.active_donors().filter(pk=self.donor.pk).exists())
        self.assertTrue(repository.active_donors().filter(pk=self.other.pk).exists())
        self.assertEqual(self.client.get(self.history_url).json()["donations"], history)

    def test_withdrawn_donor_can_be_deleted(self):
        self.donor.status = Donor.Status.WITHDRAWN
        self.donor.save(update_fields=["status"])
        self.assertEqual(self.remove(self.donor_url).status_code, 200)
        self.donor.refresh_from_db()
        self.assertEqual(self.donor.status, Donor.Status.DELETED)

    def test_donor_without_history_can_be_deleted(self):
        response = self.remove(f"/api/donors/{self.other.pk}/")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Donor.objects.filter(pk=self.other.pk, status="deleted").exists())

    def test_repeated_donor_delete_is_safe_but_deleted_entry_returns_404(self):
        self.assertEqual(self.remove(self.entry_url).status_code, 200)
        self.assertEqual(self.remove(self.entry_url).status_code, 404)
        first = self.remove(self.donor_url)
        second = self.remove(self.donor_url)
        self.assertEqual(first.data, second.data)
        self.assertEqual(second.status_code, 200)
        self.assertTrue(Donation.objects.filter(pk=self.old.pk).exists())

    def test_invalid_confirmation_leaves_everything_unchanged(self):
        for url in (self.entry_url, self.donor_url):
            for data in ({}, {"confirm": False}, {"confirm": "true"}, {"confirm": 1},
                         {"confirm": None}, [], {"confirm": True, "donor_id": self.other.pk}):
                with self.subTest(url=url, data=data):
                    self.assertEqual(self.remove(url, data).status_code, 400)
                    self.assert_unchanged()

    def test_missing_records_and_wrong_parent_return_404(self):
        urls = ["/api/donors/999999/", f"{self.donor_url}donations/999999/",
                f"/api/donors/{self.other.pk}/donations/{self.latest.pk}/",
                f"/api/donors/999999/donations/{self.latest.pk}/"]
        for url in urls:
            self.assertEqual(self.remove(url).status_code, 404)
            self.assert_unchanged()

    def test_donors_cannot_delete_even_their_own_records(self):
        for user in (self.user, self.other_user):
            self.authenticate(user)
            for url in (self.entry_url, self.donor_url):
                self.assertEqual(self.remove(url).status_code, 403)
                self.assert_unchanged()

    def test_missing_and_invalid_tokens_return_401(self):
        for token in (None, "Bearer invalid"):
            self.client.credentials(**({"HTTP_AUTHORIZATION": token} if token else {}))
            for url in (self.entry_url, self.donor_url):
                self.assertEqual(self.remove(url).status_code, 401)
                self.assert_unchanged()

    def test_inactive_coordinator_cannot_delete(self):
        self.coordinator.is_active = False
        self.coordinator.save(update_fields=["is_active"])
        for url in (self.entry_url, self.donor_url):
            self.assertEqual(self.remove(url).status_code, 401)
            self.assert_unchanged()

    def test_deleted_donor_cannot_sign_in_or_use_existing_access_token(self):
        token = str(RefreshToken.for_user(self.user).access_token)
        self.remove(self.donor_url)
        login = self.client.post("/api/auth/token/", {
            "email": self.user.email, "password": PASSWORD,
        }, format="json")
        self.assertEqual(login.status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(self.client.get("/api/donors/me/contact/").status_code, 401)
        self.assertEqual(self.client.get("/api/donors/me/eligibility/").status_code, 401)

    def test_account_save_failure_rolls_back_donor_status(self):
        with patch("accounts.models.User.save", side_effect=RuntimeError("write failed")):
            with self.assertRaises(RuntimeError):
                self.remove(self.donor_url)
        self.assert_unchanged()

    def test_calculation_failure_rolls_back_donation_deletion(self):
        with patch("donors.calculator.calculate_eligibility", side_effect=RuntimeError("failed")):
            with self.assertRaises(RuntimeError):
                self.remove(self.entry_url)
        self.assert_unchanged()

    def test_get_and_post_do_not_delete(self):
        for url in (self.entry_url, self.donor_url):
            self.assertEqual(self.client.get(url).status_code, 405)
            self.assertEqual(self.client.post(url, {"confirm": True}).status_code, 405)
            self.assert_unchanged()

    def test_service_layer_also_rejects_donor_role(self):
        from rest_framework.exceptions import PermissionDenied

        with self.assertRaises(PermissionDenied):
            services.delete_donor(self.user, self.donor.pk)
        with self.assertRaises(PermissionDenied):
            services.delete_donation(self.user, self.donor.pk, self.latest.pk)
        self.assert_unchanged()
