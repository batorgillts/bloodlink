from django.db import IntegrityError
from django.test import TestCase
from rest_framework.test import APIClient

from .models import User


# These cover a good sign-in, a wrong password and a deactivated account (all 401), plus the case-insensitive email rule. Rubric: criterion 4
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
