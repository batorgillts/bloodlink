from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from accounts.models import User
from donors import repository
from donors.models import Donation, DonationIntervalRule, Donor

PROFILE_URL = "/api/donors/me/profile/"


class DonorPortalTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("portal@example.com", "Password123")
        cls.donor = Donor.objects.create(
            user=cls.user,
            full_name="Portal Donor",
            date_of_birth=date(1998, 5, 12),
            blood_type="A+",
            phone="2025550100",
        )
        cls.other_user = User.objects.create_user("other@example.com", "Password123")
        cls.other = Donor.objects.create(
            user=cls.other_user,
            full_name="Other Donor",
            date_of_birth=date(1998, 5, 12),
            blood_type="O-",
            phone="2025550101",
        )
        cls.coordinator = User.objects.create_user(
            "private-staff@example.com",
            "Password123",
            role=User.Role.COORDINATOR,
            first_name="Jordan",
            last_name="Lee",
        )
        rule = DonationIntervalRule.objects.get(donation_type="plasma")
        cls.donation = Donation.objects.create(
            donor=cls.donor,
            donation_type=rule,
            donation_date=date(2026, 10, 1),
            blood_type="A+",
            volume_ml=600,
            recorded_by=cls.coordinator,
        )
        Donation.objects.create(
            donor=cls.other,
            donation_type=rule,
            donation_date=date(2026, 10, 2),
            blood_type="O-",
            volume_ml=600,
            recorded_by=cls.coordinator,
        )

    def setUp(self):
        self.client = APIClient()
        self.client.force_authenticate(self.user)

    def test_profile_is_own_read_only_data_without_account_secrets(self):
        response = self.client.get(PROFILE_URL, {"donor_id": self.other.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "donor_id": self.donor.pk,
                "full_name": "Portal Donor",
                "blood_type": "A+",
                "email": "portal@example.com",
                "phone": "2025550100",
                "status": "active",
            },
        )
        response = self.client.patch(PROFILE_URL, {"blood_type": "O-"}, format="json")
        self.assertEqual(response.status_code, 405)
        self.donor.refresh_from_db()
        self.assertEqual(self.donor.blood_type, "A+")

    def test_anonymous_and_coordinator_are_rejected(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(PROFILE_URL).status_code, 401)
        self.client.force_authenticate(self.coordinator)
        self.assertEqual(self.client.get(PROFILE_URL).status_code, 403)

    def test_inactive_donor_profile_is_not_disclosed(self):
        self.donor.status = Donor.Status.WITHDRAWN
        self.donor.save()
        self.assertEqual(self.client.get(PROFILE_URL).status_code, 403)

    def test_missing_profile_returns_404(self):
        user = User.objects.create_user("missing@example.com", "Password123")
        self.client.force_authenticate(user)
        self.assertEqual(self.client.get(PROFILE_URL).status_code, 404)

    def test_history_includes_recorder_name_but_no_staff_email_or_other_donor(self):
        response = self.client.get("/api/donors/me/eligibility/")
        self.assertEqual(response.status_code, 200)
        rows = response.json()["donations"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["donation_id"], self.donation.pk)
        self.assertEqual(rows[0]["recorded_by"], "Jordan Lee")
        self.assertNotIn(self.coordinator.email, str(response.json()))
        response = self.client.get(f"/api/donors/{self.other.pk}/eligibility/")
        self.assertEqual(response.status_code, 403)

    def test_unnamed_recorder_uses_stable_id_not_email(self):
        self.coordinator.first_name = ""
        self.coordinator.last_name = ""
        self.coordinator.save()
        row = self.client.get("/api/donors/me/eligibility/").json()["donations"][0]
        self.assertEqual(row["recorded_by"], f"Coordinator #{self.coordinator.pk}")

    def test_recorder_lookup_does_not_add_queries_per_donation(self):
        Donation.objects.create(
            donor=self.donor, donation_type=self.donation.donation_type,
            donation_date="2026-01-01", blood_type=self.donor.blood_type,
            volume_ml=450, recorded_by=self.coordinator,
        )
        # One history query plus one batched unit lookup, independent of row count.
        with self.assertNumQueries(2):
            rows = repository.donations_for(self.donor.pk)
            for row in rows:
                self.assertEqual(row.recorded_by.get_full_name(), "Jordan Lee")
                list(row.blood_units.all())

    def test_contact_update_is_reflected_in_profile_and_cannot_change_name(self):
        response = self.client.patch(
            "/api/donors/me/contact/",
            {"phone": "2025550199"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(PROFILE_URL).json()["phone"], "2025550199")
        response = self.client.patch(
            "/api/donors/me/contact/",
            {"full_name": "Changed"},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
