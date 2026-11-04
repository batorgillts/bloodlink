from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User

from .models import Donation, DonationIntervalRule, Donor

LIST_URL = "/api/donors/"
PASSWORD = "TestPassword123"


class DonorRecordApiTests(TestCase):
    """US-08: coordinator search, view, create, edit, and access control."""

    @classmethod
    def setUpTestData(cls):
        cls.coordinator = User.objects.create_user(
            "coordinator@example.com", PASSWORD, role=User.Role.COORDINATOR
        )
        cls.donor_user = User.objects.create_user("ana@example.com", PASSWORD)
        cls.other_user = User.objects.create_user("ben@example.com", PASSWORD)
        cls.donor = Donor.objects.create(
            user=cls.donor_user,
            full_name="Ana Lopez",
            date_of_birth=date(1995, 5, 20),
            blood_type="O-",
            phone="2125550100",
        )
        cls.other_donor = Donor.objects.create(
            user=cls.other_user,
            full_name="Ben Carter",
            date_of_birth=date(1990, 3, 15),
            blood_type="A+",
            phone="2125550200",
        )

    def setUp(self):
        self.client = APIClient()
        self.authenticate(self.coordinator)

    def authenticate(self, user):
        token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def valid_registration(self, **overrides):
        data = {
            "full_name": "Walk-in Donor",
            "email": "walkin@example.com",
            "password": PASSWORD,
            "date_of_birth": "1990-04-12",
            "blood_type": "B+",
            "phone": "2125550300",
        }
        return {**data, **overrides}

    def test_search_by_name_email_and_blood_type(self):
        by_name = self.client.get(LIST_URL, {"name": "ana"})
        by_email = self.client.get(LIST_URL, {"email": "EXAMPLE.COM"})
        by_type = self.client.get(LIST_URL, {"blood_type": "O-"})

        self.assertEqual([row["id"] for row in by_name.data], [self.donor.pk])
        self.assertEqual(len(by_email.data), 2)
        self.assertEqual([row["id"] for row in by_type.data], [self.donor.pk])

    def test_search_filters_can_be_combined(self):
        response = self.client.get(LIST_URL, {"name": "ana", "blood_type": "O-"})
        self.assertEqual([row["id"] for row in response.data], [self.donor.pk])

    def test_search_returns_only_active_donors(self):
        inactive_records = (
            ("withdrawn@example.com", Donor.Status.WITHDRAWN),
            ("deleted@example.com", Donor.Status.DELETED),
        )
        for email, donor_status in inactive_records:
            user = User.objects.create_user(email, PASSWORD)
            Donor.objects.create(
                user=user,
                full_name=email.split("@")[0],
                date_of_birth=date(1990, 1, 1),
                blood_type="A+",
                phone="2125550999",
                status=donor_status,
            )

        response = self.client.get(LIST_URL)

        result_ids = {row["id"] for row in response.data}
        self.assertEqual(result_ids, {self.donor.pk, self.other_donor.pk})
        self.assertTrue(
            all(row["status"] == Donor.Status.ACTIVE for row in response.data)
        )

    def test_detail_includes_profile_donation_history_and_eligibility(self):
        rule = DonationIntervalRule.objects.get(donation_type="whole_blood")
        Donation.objects.create(
            donor=self.donor,
            donation_type=rule,
            donation_date=timezone.localdate() - timedelta(days=56),
            blood_type=self.donor.blood_type,
            volume_ml=450,
            recorded_by=self.coordinator,
        )

        response = self.client.get(f"{LIST_URL}{self.donor.pk}/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["full_name"], "Ana Lopez")
        self.assertEqual(response.data["email"], "ana@example.com")
        self.assertEqual(len(response.data["donations"]), 1)
        whole_blood = next(
            row for row in response.data["eligibility"] if row["donation_type"] == "whole_blood"
        )
        self.assertTrue(whole_blood["eligible"])

    def test_coordinator_can_create_walk_in_donor_and_user(self):
        response = self.client.post(LIST_URL, self.valid_registration(), format="json")

        self.assertEqual(response.status_code, 201)
        user = User.objects.get(email="walkin@example.com")
        donor = Donor.objects.get(user=user)
        self.assertEqual(user.role, User.Role.DONOR)
        self.assertTrue(user.check_password(PASSWORD))
        self.assertEqual(donor.full_name, "Walk-in Donor")
        self.assertNotIn("access", response.data)
        self.assertNotIn("password", response.data)

    def test_walk_in_donor_can_sign_in_after_coordinator_creates_account(self):
        self.client.post(LIST_URL, self.valid_registration(), format="json")

        self.client.credentials()
        response = self.client.post(
            "/api/auth/token/",
            {"email": "walkin@example.com", "password": PASSWORD},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_underage_walk_in_is_rejected_without_creating_user(self):
        response = self.client.post(
            LIST_URL,
            self.valid_registration(email="underage@example.com", date_of_birth="2015-01-01"),
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("date_of_birth", response.data)
        self.assertFalse(User.objects.filter(email="underage@example.com").exists())

    def test_duplicate_email_is_rejected(self):
        response = self.client.post(
            LIST_URL,
            self.valid_registration(email="ANA@example.com"),
            format="json",
        )
        self.assertEqual(response.status_code, 409)
        self.assertEqual(User.objects.filter(email__iexact="ana@example.com").count(), 1)

    def test_invalid_email_and_phone_are_rejected(self):
        for field, value in (
            ("email", "not-an-email"),
            ("phone", "212-555-0300"),
            ("phone", "１２３４５６７８９０"),
        ):
            with self.subTest(field=field):
                changes = {field: value}
                if field != "email":
                    changes["email"] = f"new-{field}@example.com"
                response = self.client.post(
                    LIST_URL,
                    self.valid_registration(**changes),
                    format="json",
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data)

    def test_coordinator_can_edit_and_read_updated_record(self):
        response = self.client.patch(
            f"{LIST_URL}{self.donor.pk}/",
            {"full_name": "Ana Updated", "email": "ANA.NEW@example.com", "phone": "0123456789"},
            format="json",
        )

        self.assertEqual(response.status_code, 200)
        self.donor.refresh_from_db()
        self.donor_user.refresh_from_db()
        self.assertEqual(self.donor.full_name, "Ana Updated")
        self.assertEqual(self.donor_user.email, "ana.new@example.com")
        self.assertEqual(self.donor.phone, "0123456789")
        reread = self.client.get(f"{LIST_URL}{self.donor.pk}/")
        self.assertEqual(reread.data["full_name"], "Ana Updated")

    def test_invalid_email_or_phone_edit_is_rejected_without_saving(self):
        for field, value in (("email", "bad-email"), ("phone", "123")):
            with self.subTest(field=field):
                response = self.client.patch(
                    f"{LIST_URL}{self.donor.pk}/",
                    {field: value},
                    format="json",
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn(field, response.data)
                self.donor.refresh_from_db()
                self.donor_user.refresh_from_db()
                self.assertEqual(self.donor.phone, "2125550100")
                self.assertEqual(self.donor_user.email, "ana@example.com")

    def test_donor_cannot_search_view_create_or_edit_records(self):
        self.authenticate(self.donor_user)
        requests = (
            self.client.get(LIST_URL),
            self.client.get(f"{LIST_URL}{self.other_donor.pk}/"),
            self.client.post(LIST_URL, self.valid_registration(), format="json"),
            self.client.patch(
                f"{LIST_URL}{self.other_donor.pk}/", {"phone": "2125550999"}, format="json"
            ),
        )
        self.assertEqual([response.status_code for response in requests], [403, 403, 403, 403])

    def test_unauthenticated_search_is_denied(self):
        self.client.credentials()
        self.assertEqual(self.client.get(LIST_URL).status_code, 401)
        self.assertEqual(self.client.get(f"{LIST_URL}{self.donor.pk}/").status_code, 401)

    def test_unknown_donor_detail_returns_404(self):
        response = self.client.get(f"{LIST_URL}999999/")
        self.assertEqual(response.status_code, 404)

