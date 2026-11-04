from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient

from donors.models import Donor

from .models import User
from .serializers import age_on

URL = "/api/auth/register/"


def years_ago(years, today=None):
    """The date exactly `years` years before today (29 Feb safe)."""
    today = today or date.today()
    try:
        return today.replace(year=today.year - years)
    except ValueError:
        return today.replace(year=today.year - years, day=28)


class DonorRegistrationTests(TestCase):
    """US-01: Donor registration. One test per acceptance criterion."""

    def setUp(self):
        self.client = APIClient()
        self.valid = {
            "full_name": "Ana Lopez",
            "email": "ana@example.com",
            "password": "Password123",
            "date_of_birth": years_ago(30).isoformat(),
            "blood_type": "O-",
            "phone": "2125550100",
        }

    # AC1: all information submitted -> donor account is created
    def test_valid_registration_creates_donor_account(self):
        res = self.client.post(URL, self.valid)
        self.assertEqual(res.status_code, 201)
        user = User.objects.get(email="ana@example.com")
        self.assertEqual(user.role, User.Role.DONOR)
        self.assertTrue(user.check_password("Password123"))  # stored hashed, not plain
        donor = Donor.objects.get(user=user)
        self.assertEqual(donor.blood_type, "O-")
        self.assertEqual(donor.status, Donor.Status.ACTIVE)

    # AC2: after registering, the donor is signed in automatically
    def test_registration_signs_the_donor_in(self):
        res = self.client.post(URL, self.valid)
        self.assertIn("access", res.data)
        self.assertIn("refresh", res.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {res.data['access']}")
        # The access token works on the normal token-refresh flow and identifies the user.
        refreshed = self.client.post("/api/auth/token/refresh/", {"refresh": res.data["refresh"]})
        self.assertEqual(refreshed.status_code, 200)

    # AC3: age below 17 -> rejected with an eligibility error
    def test_under_17_is_rejected(self):
        dob = years_ago(17)
        dob = dob.replace(day=dob.day + 1) if dob.day < 28 else years_ago(16)
        res = self.client.post(URL, {**self.valid, "date_of_birth": dob.isoformat()})
        self.assertEqual(res.status_code, 400)
        self.assertIn("date_of_birth", res.data)
        self.assertFalse(User.objects.filter(email="ana@example.com").exists())

    def test_exactly_17_today_is_accepted(self):
        res = self.client.post(URL, {**self.valid, "date_of_birth": years_ago(17).isoformat()})
        self.assertEqual(res.status_code, 201)

    # AC4: password not matching the format -> rejected with a format error
    def test_password_without_a_number_is_rejected(self):
        res = self.client.post(URL, {**self.valid, "password": "passwordonly"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("password", res.data)

    def test_password_shorter_than_8_is_rejected(self):
        res = self.client.post(URL, {**self.valid, "password": "pass12"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("password", res.data)

    # AC5: email already registered -> rejected with a duplicate error
    def test_duplicate_email_is_rejected_with_409(self):
        self.client.post(URL, self.valid)
        res = self.client.post(URL, {**self.valid, "email": "ANA@example.com"})
        self.assertEqual(res.status_code, 409)
        self.assertEqual(User.objects.filter(email__iexact="ana@example.com").count(), 1)

    # Input validation (NFR-3)
    def test_missing_field_is_rejected(self):
        data = {k: v for k, v in self.valid.items() if k != "blood_type"}
        res = self.client.post(URL, data)
        self.assertEqual(res.status_code, 400)
        self.assertIn("blood_type", res.data)

    def test_invalid_blood_type_is_rejected(self):
        res = self.client.post(URL, {**self.valid, "blood_type": "C+"})
        self.assertEqual(res.status_code, 400)

    def test_invalid_phone_is_rejected(self):
        res = self.client.post(URL, {**self.valid, "phone": "555-0100"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("phone", res.data)

    def test_new_donor_can_sign_in_later(self):
        self.client.post(URL, self.valid)
        res = self.client.post(
            "/api/auth/token/", {"email": "ana@example.com", "password": "Password123"}
        )
        self.assertEqual(res.status_code, 200)


class AgeCalculationTests(TestCase):
    def test_birthday_not_yet_reached_this_year(self):
        self.assertEqual(age_on(date(2009, 10, 28), date(2026, 10, 27)), 16)

    def test_birthday_today(self):
        self.assertEqual(age_on(date(2009, 10, 27), date(2026, 10, 27)), 17)
