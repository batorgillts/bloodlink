from django.db import IntegrityError
from django.test import TestCase
from rest_framework.test import APIClient

from .models import User


# Covers valid sign-in, wrong password and deactivated account (all 401),
# plus the case-insensitive unique email rule.
class SignInTests(TestCase):
    """Token sign-in for both roles (US-02, US-06) and NFR-1."""

    def setUp(self):
        self.client = APIClient()
        User.objects.create_user("coord@bloodlink.test", "Password123", role=User.Role.COORDINATOR)

    def test_valid_credentials_return_tokens(self):
        res = self.client.post(
            "/api/auth/token/", {"email": "coord@bloodlink.test", "password": "Password123"}
        )
        self.assertEqual(res.status_code, 200)
        self.assertIn("access", res.data)

    def test_wrong_password_returns_401(self):
        res = self.client.post(
            "/api/auth/token/", {"email": "coord@bloodlink.test", "password": "wrong"}
        )
        self.assertEqual(res.status_code, 401)

    def test_deactivated_account_cannot_sign_in(self):
        User.objects.filter(email="coord@bloodlink.test").update(is_active=False)
        res = self.client.post(
            "/api/auth/token/", {"email": "coord@bloodlink.test", "password": "Password123"}
        )
        self.assertEqual(res.status_code, 401)

    def test_email_is_unique_ignoring_case(self):
        with self.assertRaises(IntegrityError):
            User.objects.create(email="COORD@bloodlink.test")


class SignInRoleTests(TestCase):
    """US-02 (donor) and US-06 (coordinator) each sign in and get their role back."""

    def setUp(self):
        self.client = APIClient()
        User.objects.create_user("donor@bloodlink.test", "Password123", role=User.Role.DONOR)
        User.objects.create_user("coord@bloodlink.test", "Password123", role=User.Role.COORDINATOR)

    def sign_in(self, email, password="Password123"):
        return self.client.post("/api/auth/token/", {"email": email, "password": password})

    def test_donor_signs_in_and_gets_donor_role(self):
        res = self.sign_in("donor@bloodlink.test")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["role"], "donor")
        self.assertIn("access", res.data)

    def test_coordinator_signs_in_and_gets_coordinator_role(self):
        res = self.sign_in("coord@bloodlink.test")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["role"], "coordinator")

    def test_email_is_case_insensitive_at_sign_in(self):
        self.assertEqual(self.sign_in("  DONOR@BloodLink.test ").status_code, 200)

    def test_email_changed_outside_sign_up_is_saved_lowercase(self):
        # Like an admin editing the email in the admin panel.
        user = User.objects.get(email="donor@bloodlink.test")
        user.email = "A@Example.com"
        user.save()
        user.refresh_from_db()
        self.assertEqual(user.email, "a@example.com")
        self.assertEqual(self.sign_in("A@example.com").status_code, 200)

    def test_missing_password_returns_400(self):
        res = self.client.post("/api/auth/token/", {"email": "donor@bloodlink.test"})
        self.assertEqual(res.status_code, 400)

    def test_donor_token_cannot_use_coordinator_endpoint(self):
        token = self.sign_in("donor@bloodlink.test").data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(self.client.get("/api/donors/").status_code, 403)
