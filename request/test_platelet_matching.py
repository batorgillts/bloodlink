from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from config.choices import BloodType, Component
from inventory.models import BloodUnit, CompatibilityRule

from .models import BloodRequest, Reservation


class PlateletMatchingTests(TestCase):
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
            component=Component.PLATELETS,
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
            "component": Component.PLATELETS,
            "collected_at": self.now - timedelta(days=1),
            "expires_at": self.now + timedelta(days=4),
            "created_by": self.coordinator,
        }
        values.update(overrides)
        return BloodUnit.objects.create(**values)

    def test_all_eight_recipient_types_use_agreed_abo_rules_and_ignore_rh(self):
        for blood_type in BloodType.values:
            self.unit(blood_type)
        expected = {
            "A": {"A+", "A-", "O+", "O-"},
            "B": {"B+", "B-", "O+", "O-"},
            "AB": set(BloodType.values),
            "O": {"O+", "O-"},
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
        substitute = self.unit("O+", expires_at=self.now + timedelta(days=1))
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
        self.unit(component=Component.PLASMA)
        self.unit(status=BloodUnit.Status.RESERVED)
        self.unit(status=BloodUnit.Status.DISCARDED, discard_reason="damaged")
        self.unit(status=BloodUnit.Status.EXPIRED)
        self.unit(expires_at=self.now - timedelta(seconds=1))
        self.unit(expires_at=self.now)
        with patch("inventory.models.timezone.now", return_value=self.now):
            response = self.client.get(self.url)
        self.assertEqual([row["id"] for row in response.data["units"]], [valid.pk])

    def test_empty_result_has_required_message(self):
        self.unit("AB+")
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["units"], [])
        self.assertEqual(response.data["message"], "No compatible units available")

    def test_matching_reads_configured_rules(self):
        self.unit("O+")
        CompatibilityRule.objects.filter(
            component=Component.PLATELETS, request_blood_type="A+", unit_blood_type="O+"
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

    def test_a_positive_example_labels_substitutes_and_identical_units(self):
        substitute = self.unit("O+", expires_at=self.now + timedelta(days=1))
        identical = self.unit("A+")
        rows = self.client.get(self.url).data["units"]
        self.assertEqual([row["id"] for row in rows], [identical.pk, substitute.pk])
        self.assertEqual(
            [row["match_label"] for row in rows], ["ABO-identical", "ABO-compatible, not identical"]
        )

    def test_substitutes_returned_and_labelled_without_identical_stock(self):
        unit = self.unit("O-")
        rows = self.client.get(self.url).data["units"]
        self.assertEqual([row["id"] for row in rows], [unit.pk])
        self.assertFalse(rows[0]["is_identical"])
        self.assertEqual(rows[0]["match_label"], "ABO-compatible, not identical")

    def test_negative_recipient_accepts_positive_same_abo_as_identical(self):
        self.request.blood_type = "A-"
        self.request.save()
        unit = self.unit("A+")
        row = self.client.get(self.url).data["units"][0]
        self.assertEqual(row["id"], unit.pk)
        self.assertTrue(row["is_identical"])
        self.assertEqual(row["match_label"], "ABO-identical")

    def test_substitute_group_sorted_by_expiry_not_abo(self):
        self.request.blood_type = "AB+"
        self.request.save()
        late = self.unit("O+", expires_at=self.now + timedelta(days=3))
        early = self.unit("B-", expires_at=self.now + timedelta(days=1))
        middle = self.unit("A+", expires_at=self.now + timedelta(days=2))
        rows = self.client.get(self.url).data["units"]
        self.assertEqual([row["id"] for row in rows], [early.pk, middle.pk, late.pk])

    def test_discard_api_removes_unit_from_matching(self):
        unit = self.unit()
        self.assertEqual(len(self.client.get(self.url).data["units"]), 1)
        response = self.client.post(
            f"/api/units/{unit.pk}/discard/", {"reason": "damaged"}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(self.url).data["units"], [])

    def test_cancellation_releases_only_unexpired_units_back_to_matching(self):
        other = BloodRequest.objects.create(
            blood_type="A+",
            component=Component.PLATELETS,
            quantity=3,
            logged_by=self.coordinator,
            status=BloodRequest.Status.PARTIALLY_FULFILLED,
        )
        valid = self.unit(status=BloodUnit.Status.RESERVED)
        expired = self.unit(
            status=BloodUnit.Status.RESERVED, expires_at=self.now - timedelta(seconds=1)
        )
        for unit in (valid, expired):
            Reservation.objects.create(request=other, unit=unit, reserved_by=self.coordinator)
        self.assertEqual(self.client.get(self.url).data["units"], [])
        response = self.client.post(
            f"/api/requests/{other.pk}/cancel/", {"confirm": True}, format="json"
        )
        self.assertEqual(response.status_code, 200)
        rows = self.client.get(self.url).data["units"]
        self.assertEqual([row["id"] for row in rows], [valid.pk])

    def test_other_components_keep_rules_and_response_fields(self):
        for component, expected_types in (
            (Component.RED_BLOOD_CELLS, {"A-", "O-"}),
            (Component.PLASMA, {"A+", "A-", "AB+", "AB-"}),
        ):
            with self.subTest(component=component):
                for blood_type in BloodType.values:
                    self.unit(blood_type, component=component)
                self.request.component = component
                self.request.blood_type = "A-"
                self.request.save()
                response = self.client.get(self.url)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(
                    {row["blood_type"] for row in response.data["units"]}, expected_types
                )
                for row in response.data["units"]:
                    self.assertNotIn("match_label", row)
