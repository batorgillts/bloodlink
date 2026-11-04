from datetime import date
from unittest.mock import patch

from django.db import IntegrityError
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User

from .models import Donor

URL = "/api/donors/me/contact/"
PASSWORD = "TestPassword123"


class DonorContactTests(TestCase):
    """US-03 AC1-AC5, plus the Sprint 2 validation and permission contract."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("alice@example.com", PASSWORD)
        cls.other = User.objects.create_user("bob@example.com", PASSWORD)
        cls.coordinator = User.objects.create_user(
            "coord@example.com", PASSWORD, role=User.Role.COORDINATOR
        )
        cls.donor = Donor.objects.create(
            user=cls.user, full_name="Alice Demo", date_of_birth=date(1995, 5, 20),
            blood_type="O+", phone="2125550100",
        )
        cls.other_donor = Donor.objects.create(
            user=cls.other, full_name="Bob Demo", date_of_birth=date(1996, 4, 10),
            blood_type="A+", phone="2125550200",
        )

    def setUp(self):
        self.client = APIClient()
        self.authenticate(self.user)

    def authenticate(self, user):
        token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def assert_contact_unchanged(self):
        self.user.refresh_from_db()
        self.donor.refresh_from_db()
        self.assertEqual(self.user.email, "alice@example.com")
        self.assertEqual(self.donor.phone, "2125550100")

    # AC1: the current donor sees only their own contact fields.
    def test_get_current_contact(self):
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {
            "donor_id": self.donor.pk, "email": "alice@example.com", "phone": "2125550100",
        })

    def test_get_own_contact_by_donor_id(self):
        response = self.client.get(f"/api/donors/{self.donor.pk}/contact/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["email"], self.user.email)

    # AC2: an invalid email must not result in a partial phone update.
    def test_invalid_emails_rejected_without_saving(self):
        for email in ["not-an-email", "alice@", "", None, "x" * 255 + "@example.com"]:
            with self.subTest(email=email):
                response = self.client.patch(
                    URL, {"email": email, "phone": "2125550999"}, format="json"
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("email", response.data)
                self.assert_contact_unchanged()

    # AC3: 10 digits, with no punctuation, whitespace, or dropped leading zero.
    def test_invalid_phones_rejected_without_saving(self):
        for phone in ["123456789", "12345678901", "212-555-0100", "abcdefghij",
                      "2125550100\n", " 2125550100", "", None]:
            with self.subTest(phone=phone):
                response = self.client.patch(
                    URL, {"email": "updated@example.com", "phone": phone}, format="json"
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn("phone", response.data)
                self.assert_contact_unchanged()

    # AC4: save, then read the database and the endpoint again.
    def test_update_both_fields_and_read_again(self):
        response = self.client.patch(
            URL, {"email": "UPDATED@Example.com", "phone": "0123456789"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.user.refresh_from_db()
        self.donor.refresh_from_db()
        self.assertEqual(self.user.email, "updated@example.com")
        self.assertEqual(self.donor.phone, "0123456789")
        self.assertEqual(self.client.get(URL).json(), response.json())
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_phone_only_preserves_email(self):
        response = self.client.patch(URL, {"phone": "2125550999"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["email"], self.user.email)
        self.assertEqual(response.data["phone"], "2125550999")

    def test_email_only_preserves_phone_and_changes_sign_in_email(self):
        response = self.client.patch(URL, {"email": "new@example.com"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["phone"], self.donor.phone)
        self.client.credentials()
        old = self.client.post("/api/auth/token/", {
            "email": "alice@example.com", "password": PASSWORD,
        })
        new = self.client.post("/api/auth/token/", {
            "email": "new@example.com", "password": PASSWORD,
        })
        self.assertEqual(old.status_code, 401)
        self.assertEqual(new.status_code, 200)

    def test_patch_own_id(self):
        response = self.client.patch(
            f"/api/donors/{self.donor.pk}/contact/", {"phone": "2125550999"}, format="json"
        )
        self.assertEqual(response.status_code, 200)

    # AC5 / NFR-5: direct URL manipulation cannot read or change another donor.
    def test_other_donor_get_and_patch_return_403_without_disclosure(self):
        url = f"/api/donors/{self.other_donor.pk}/contact/"
        for method in ["get", "patch"]:
            with self.subTest(method=method):
                response = getattr(self.client, method)(
                    url, {"phone": "2125550999"}, format="json"
                )
                self.assertEqual(response.status_code, 403)
                self.assertNotIn(self.other.email, str(response.data))
                self.assertNotIn(self.other_donor.phone, str(response.data))
        self.other_donor.refresh_from_db()
        self.assertEqual(self.other_donor.phone, "2125550200")
        self.assert_contact_unchanged()

    def test_unknown_donor_id_is_also_denied(self):
        response = self.client.get("/api/donors/999999/contact/")
        self.assertEqual(response.status_code, 403)

    def test_me_url_cannot_be_retargeted_by_query_string(self):
        response = self.client.get(URL, {"donor_id": self.other_donor.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["donor_id"], self.donor.pk)

    # NFR-1: use actual JWT authentication, not force_authenticate.
    def test_unauthenticated_get_and_patch_return_401(self):
        self.client.credentials()
        for method in ["get", "patch"]:
            response = getattr(self.client, method)(URL, {"phone": "2125550999"})
            self.assertEqual(response.status_code, 401)
        self.assert_contact_unchanged()

    def test_invalid_token_returns_401(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalid-token")
        self.assertEqual(self.client.get(URL).status_code, 401)

    def test_deactivated_account_token_returns_401(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertEqual(self.client.get(URL).status_code, 401)

    def test_coordinator_get_and_patch_return_403(self):
        self.authenticate(self.coordinator)
        for method in ["get", "patch"]:
            response = getattr(self.client, method)(URL, {"phone": "2125550999"})
            self.assertEqual(response.status_code, 403)

    def test_withdrawn_or_deleted_profile_is_denied(self):
        for status in [Donor.Status.WITHDRAWN, Donor.Status.DELETED]:
            self.donor.status = status
            self.donor.save(update_fields=["status"])
            for method in ["get", "patch"]:
                response = getattr(self.client, method)(URL, {"phone": "2125550999"})
                self.assertEqual(response.status_code, 403)

    def test_missing_profile_returns_404(self):
        self.donor.delete()
        self.assertEqual(self.client.get(URL).status_code, 404)

    def test_duplicate_email_returns_409_and_preserves_both_fields(self):
        response = self.client.patch(
            URL, {"email": "BOB@EXAMPLE.COM", "phone": "2125550999"}, format="json"
        )
        self.assertEqual(response.status_code, 409)
        self.assertIn("email", response.data)
        self.assert_contact_unchanged()

    def test_own_email_is_not_a_duplicate(self):
        response = self.client.patch(URL, {"email": "ALICE@EXAMPLE.COM"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assert_contact_unchanged()

    def test_database_unique_constraint_race_returns_409(self):
        # Simulate the pre-check missing a competing update. The real database
        # constraint still rejects the email, and the transaction rolls back.
        with patch("donors.repository.email_in_use", side_effect=[False, True]):
            response = self.client.patch(
                URL, {"email": self.other.email, "phone": "2125550999"}, format="json"
            )
        self.assertEqual(response.status_code, 409)
        self.assert_contact_unchanged()

    def test_failed_phone_write_rolls_back_email_too(self):
        with patch.object(Donor, "save", side_effect=IntegrityError("simulated write failure")):
            with self.assertRaises(IntegrityError):
                self.client.patch(
                    URL, {"email": "new@example.com", "phone": "2125550999"}, format="json"
                )
        self.assert_contact_unchanged()

    def test_empty_update_rejected(self):
        self.assertEqual(self.client.patch(URL, {}, format="json").status_code, 400)

    def test_non_object_input_rejected(self):
        self.assertEqual(self.client.patch(URL, [], format="json").status_code, 400)

    def test_unknown_and_privileged_fields_rejected_without_any_change(self):
        for key, value in {
            "user_id": self.other.pk, "donor_id": self.other_donor.pk,
            "role": "coordinator", "is_staff": True, "password": "Changed123",
            "blood_type": "AB+", "status": "deleted",
        }.items():
            with self.subTest(key=key):
                response = self.client.patch(
                    URL, {key: value, "phone": "2125550999"}, format="json"
                )
                self.assertEqual(response.status_code, 400)
                self.assertIn(key, response.data)
                self.assert_contact_unchanged()
        self.assertEqual(self.user.role, User.Role.DONOR)
        self.assertFalse(self.user.is_staff)
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_registration_tokens_work_for_contact_endpoint(self):
        self.client.credentials()
        registered = self.client.post("/api/auth/register/", {
            "full_name": "Carol Demo", "email": "carol@example.com", "password": PASSWORD,
            "date_of_birth": "1990-06-15", "blood_type": "B+", "phone": "2125550300",
        }, format="json")
        self.assertEqual(registered.status_code, 201)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {registered.data['access']}")
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["email"], "carol@example.com")
        updated = self.client.patch(URL, {"phone": "2125550400"}, format="json")
        self.assertEqual(updated.status_code, 200)
        self.assertEqual(self.client.get(URL).data["phone"], "2125550400")

    def test_delete_is_not_supported(self):
        self.assertEqual(self.client.delete(URL).status_code, 405)
        self.assertTrue(Donor.objects.filter(pk=self.donor.pk).exists())
