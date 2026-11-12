from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from config.choices import BloodType, Component
from inventory.models import BloodUnit, CompatibilityRule

from .models import BloodRequest

# Recipient type -> unit types that are safe for a red-cell transfusion.
RBC_COMPATIBLE = {
    "O-": {"O-"},
    "O+": {"O-", "O+"},
    "A-": {"O-", "A-"},
    "A+": {"O-", "O+", "A-", "A+"},
    "B-": {"O-", "B-"},
    "B+": {"O-", "O+", "B-", "B+"},
    "AB-": {"O-", "A-", "B-", "AB-"},
    "AB+": set(BloodType.values),
}


class RbcMatchingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.coordinator = User.objects.create_user(
            "rbc-coordinator@example.com", "TestPassword123", role=User.Role.COORDINATOR
        )
        cls.donor = User.objects.create_user("rbc-donor@example.com", "TestPassword123")

    def setUp(self):
        self.client = APIClient()
        self.authenticate(self.coordinator)
        self.now = timezone.now()
        self.request = BloodRequest.objects.create(
            blood_type="A+",
            component=Component.RED_BLOOD_CELLS,
            quantity=1,
            logged_by=self.coordinator,
        )
        self.url = f"/api/requests/{self.request.pk}/matches/"

    def authenticate(self, user):
        token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def unit(self, blood_type="A+", **overrides):
        values = {
            "unit_code": f"RBC-{BloodUnit.objects.count() + 1}",
            "blood_type": blood_type,
            "component": Component.RED_BLOOD_CELLS,
            "collected_at": self.now - timedelta(days=1),
            "expires_at": self.now + timedelta(days=10),
            "created_by": self.coordinator,
        }
        values.update(overrides)
        return BloodUnit.objects.create(**values)

    def test_all_eight_recipient_types_follow_abo_rh_rules(self):
        for blood_type in BloodType.values:
            self.unit(blood_type)
        for blood_type in BloodType.values:
            with self.subTest(recipient=blood_type):
                self.request.blood_type = blood_type
                self.request.save()
                response = self.client.get(self.url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    {row["blood_type"] for row in response.data["units"]},
                    RBC_COMPATIBLE[blood_type],
                )

    def test_a_positive_example_returns_only_a_and_o_units(self):
        for blood_type in BloodType.values:
            self.unit(blood_type)
        response = self.client.get(self.url)
        self.assertEqual(
            {row["blood_type"] for row in response.data["units"]},
            {"A+", "A-", "O+", "O-"},
        )

    def test_o_negative_request_returns_only_o_negative_units(self):
        for blood_type in BloodType.values:
            self.unit(blood_type)
        self.request.blood_type = "O-"
        self.request.save()
        response = self.client.get(self.url)
        self.assertEqual([row["blood_type"] for row in response.data["units"]], ["O-"])

    def test_exact_type_first_then_expiry_with_stable_ties(self):
        substitute = self.unit("O-", expires_at=self.now + timedelta(days=1))
        later = self.unit("A+", expires_at=self.now + timedelta(days=5))
        earlier = self.unit("A+", expires_at=self.now + timedelta(days=2))
        tied = self.unit("A+", expires_at=earlier.expires_at)
        response = self.client.get(self.url)
        self.assertEqual(
            [row["id"] for row in response.data["units"]],
            [earlier.pk, tied.pk, later.pk, substitute.pk],
        )
        self.assertEqual(
            [row["is_identical"] for row in response.data["units"]],
            [True, True, True, False],
        )
        self.assertIn("unit_code", response.data["units"][0])
        self.assertIn("blood_type", response.data["units"][0])
        self.assertIn("expires_at", response.data["units"][0])

    def test_excludes_other_components_and_unusable_units_including_expiry_boundary(self):
        valid = self.unit()
        self.unit(component=Component.PLASMA)
        self.unit(component=Component.PLATELETS)
        self.unit(status=BloodUnit.Status.RESERVED)
        self.unit(status=BloodUnit.Status.DISCARDED, discard_reason="damaged")
        self.unit(status=BloodUnit.Status.EXPIRED)
        self.unit(expires_at=self.now - timedelta(seconds=1))
        self.unit(expires_at=self.now)
        with patch("inventory.models.timezone.now", return_value=self.now):
            response = self.client.get(self.url)
        self.assertEqual([row["id"] for row in response.data["units"]], [valid.pk])

    def test_empty_result_has_required_message(self):
        self.unit("B+")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["units"], [])
        self.assertEqual(response.data["message"], "No compatible units available")

    def test_matching_reads_configured_rules(self):
        self.unit("O-")
        CompatibilityRule.objects.filter(
            component=Component.RED_BLOOD_CELLS,
            request_blood_type="A+",
            unit_blood_type="O-",
        ).delete()
        self.assertEqual(self.client.get(self.url).data["units"], [])

    def test_matching_returns_all_units_without_reserving_or_changing_request(self):
        units = [self.unit(), self.unit()]
        for _ in range(2):
            response = self.client.get(self.url)
            self.assertEqual(len(response.data["units"]), 2)
        self.request.refresh_from_db()
        self.assertEqual(self.request.status, BloodRequest.Status.PENDING)
        for unit in units:
            unit.refresh_from_db()
            self.assertEqual(unit.status, BloodUnit.Status.AVAILABLE)

    def test_donor_is_denied(self):
        self.authenticate(self.donor)
        self.assertEqual(self.client.get(self.url).status_code, 403)

    def test_anonymous_is_denied(self):
        self.client.credentials()
        self.assertEqual(self.client.get(self.url).status_code, 401)

    def test_missing_request_is_not_found(self):
        self.assertEqual(self.client.get("/api/requests/999999/matches/").status_code, 404)
