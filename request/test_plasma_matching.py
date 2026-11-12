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


class PlasmaMatchingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.coordinator = User.objects.create_user(
            "coordinator@example.com", "TestPassword123", role=User.Role.COORDINATOR
        )
        cls.donor = User.objects.create_user("donor@example.com", "TestPassword123")

    def setUp(self):
        self.client = APIClient()
        self.authenticate(self.coordinator)
        self.now = timezone.now()
        self.request = BloodRequest.objects.create(
            blood_type="A+",
            component=Component.PLASMA,
            quantity=1,
            logged_by=self.coordinator,
        )
        self.url = f"/api/requests/{self.request.pk}/matches/"

    def authenticate(self, user):
        token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def unit(self, blood_type="A+", **overrides):
        values = {
            "unit_code": f"UNIT-{BloodUnit.objects.count() + 1}",
            "blood_type": blood_type,
            "component": Component.PLASMA,
            "collected_at": self.now - timedelta(days=1),
            "expires_at": self.now + timedelta(days=10),
            "created_by": self.coordinator,
        }
        values.update(overrides)
        return BloodUnit.objects.create(**values)

    def test_all_eight_recipient_types_use_reversed_abo_and_ignore_rh(self):
        for blood_type in BloodType.values:
            self.unit(blood_type)
        expected = {
            "A": {"A+", "A-", "AB+", "AB-"},
            "B": {"B+", "B-", "AB+", "AB-"},
            "AB": {"AB+", "AB-"},
            "O": set(BloodType.values),
        }
        for blood_type in BloodType.values:
            with self.subTest(recipient=blood_type):
                self.request.blood_type = blood_type
                self.request.save()
                response = self.client.get(self.url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    {row["blood_type"] for row in response.data["units"]},
                    expected[blood_type[:-1]],
                )

    def test_identical_abo_first_then_expiry_with_stable_ties(self):
        substitute = self.unit("AB+", expires_at=self.now + timedelta(days=1))
        later = self.unit("A+", expires_at=self.now + timedelta(days=5))
        earlier = self.unit("A-", expires_at=self.now + timedelta(days=2))
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
        self.assertIn("expires_at", response.data["units"][0])

    def test_excludes_other_components_and_unusable_units_including_expiry_boundary(self):
        valid = self.unit()
        self.unit(component=Component.RED_BLOOD_CELLS)
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
        self.unit("O+")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["units"], [])
        self.assertEqual(response.data["message"], "No compatible units available")

    def test_matching_reads_configured_rules(self):
        self.unit("AB+")
        CompatibilityRule.objects.filter(
            component=Component.PLASMA, request_blood_type="A+", unit_blood_type="AB+"
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

    def test_platelets_use_their_own_rules_instead_of_plasma_rules(self):
        self.request.component = Component.PLATELETS
        self.request.save()
        allowed = self.unit("O+", component=Component.PLATELETS)
        self.unit("AB+", component=Component.PLATELETS)
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data["units"]], [allowed.pk])
