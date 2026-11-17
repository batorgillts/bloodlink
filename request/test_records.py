from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from inventory.models import BloodUnit

from .models import BloodRequest

LIST_URL = "/api/requests/"
PASSWORD = "TestPassword123"


class BloodRequestApiTests(TestCase):
    """US-11: coordinator request logging, listing, and permissions."""

    @classmethod
    def setUpTestData(cls):
        cls.coordinator = User.objects.create_user(
            "coordinator@example.com", PASSWORD, role=User.Role.COORDINATOR
        )
        cls.donor = User.objects.create_user("donor@example.com", PASSWORD)

    def setUp(self):
        self.client = APIClient()
        self.authenticate(self.coordinator)

    def authenticate(self, user):
        token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def make_request(self, **overrides):
        values = {
            "logged_by": self.coordinator,
            "blood_type": "O-",
            "component": "RBC",
            "quantity": 2,
        }
        values.update(overrides)
        return BloodRequest.objects.create(**values)

    def make_unit(self, blood_type, expires_at):
        return BloodUnit.objects.create(
            unit_code=f"US11-MATCH-{BloodUnit.objects.count() + 1}",
            blood_type=blood_type,
            component="RBC",
            collected_at=timezone.now() - timedelta(days=1),
            expires_at=expires_at,
            created_by=self.coordinator,
        )

    def test_coordinator_can_log_request_with_pending_status_and_audit_fields(self):
        response = self.client.post(
            LIST_URL,
            {
                "blood_type": "O-",
                "component": "RBC",
                "quantity": 3,
                "status": "fulfilled",
                "logged_by": self.donor.pk,
            },
            format="json",
        )

        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.data["status"], BloodRequest.Status.PENDING)
        self.assertEqual(response.data["quantity"], 3)
        self.assertTrue(response.data["logged_at"])
        self.assertEqual(response.data["logged_by"], self.coordinator.pk)

        record = BloodRequest.objects.get(pk=response.data["id"])
        self.assertEqual(record.status, BloodRequest.Status.PENDING)
        self.assertEqual(record.logged_by, self.coordinator)
        self.assertIsNotNone(record.logged_at)

        list_response = self.client.get(LIST_URL)

        self.assertEqual(list_response.status_code, 200)
        self.assertIn(record.pk, {row["id"] for row in list_response.data})

    def test_missing_or_invalid_required_values_are_rejected(self):
        invalid_payloads = (
            {},
            {"blood_type": "O-", "component": "RBC"},
            {"blood_type": "invalid", "component": "RBC", "quantity": 1},
            {"blood_type": "O-", "component": "WHOLE_BLOOD", "quantity": 1},
            {"blood_type": "O-", "component": "RBC", "quantity": 0},
            {"blood_type": "O-", "component": "RBC", "quantity": -1},
        )

        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                response = self.client.post(LIST_URL, payload, format="json")
                self.assertEqual(response.status_code, 400)

        self.assertEqual(BloodRequest.objects.count(), 0)

    def test_list_returns_all_requests_regardless_of_status(self):
        self.make_request(status=BloodRequest.Status.PENDING)
        self.make_request(status=BloodRequest.Status.PARTIALLY_FULFILLED)
        self.make_request(status=BloodRequest.Status.FULFILLED)
        self.make_request(status=BloodRequest.Status.CANCELLED)

        response = self.client.get(LIST_URL)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 4)
        self.assertEqual(
            {row["status"] for row in response.data},
            set(BloodRequest.Status.values),
        )
        self.assertEqual(
            {row["id"] for row in response.data},
            set(BloodRequest.objects.values_list("id", flat=True)),
        )

    def test_list_can_filter_by_status(self):
        pending_ids = {
            self.make_request(status=BloodRequest.Status.PENDING).pk,
            self.make_request(status=BloodRequest.Status.PENDING).pk,
        }
        self.make_request(status=BloodRequest.Status.PARTIALLY_FULFILLED)
        self.make_request(status=BloodRequest.Status.FULFILLED)
        self.make_request(status=BloodRequest.Status.CANCELLED)

        response = self.client.get(LIST_URL, {"status": BloodRequest.Status.PENDING})

        self.assertEqual(response.status_code, 200)
        self.assertEqual({row["id"] for row in response.data}, pending_ids)
        self.assertEqual({row["status"] for row in response.data}, {BloodRequest.Status.PENDING})

    def test_list_can_filter_by_multiple_statuses(self):
        pending = self.make_request(status=BloodRequest.Status.PENDING)
        partial = self.make_request(status=BloodRequest.Status.PARTIALLY_FULFILLED)
        fulfilled = self.make_request(status=BloodRequest.Status.FULFILLED)
        self.make_request(status=BloodRequest.Status.CANCELLED)

        response = self.client.get(
            f"{LIST_URL}?status=pending&status=partially_fulfilled&status=fulfilled"
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            {row["id"] for row in response.data},
            {pending.pk, partial.pk, fulfilled.pk},
        )

    def test_list_rejects_unknown_status_and_lists_allowed_values(self):
        response = self.client.get(LIST_URL, {"status": "lost"})

        self.assertEqual(response.status_code, 400)
        error = str(response.data["status"])
        for allowed in BloodRequest.Status.values:
            self.assertIn(allowed, error)

    def test_matching_prioritizes_exact_type_and_excludes_expired_units(self):
        now = timezone.now()
        blood_request = self.make_request(blood_type="A+", component="RBC")
        substitute = self.make_unit("O-", now + timedelta(days=1))
        exact = self.make_unit("A+", now + timedelta(days=2))
        expired_exact = self.make_unit("A+", now - timedelta(seconds=1))

        response = self.client.get(f"{LIST_URL}{blood_request.pk}/matches/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row["id"] for row in response.data["units"]],
            [exact.pk, substitute.pk],
        )
        self.assertEqual(
            [row["is_identical"] for row in response.data["units"]],
            [True, False],
        )
        self.assertNotIn(
            expired_exact.pk,
            {row["id"] for row in response.data["units"]},
        )

    def test_matching_returns_substitutes_when_exact_type_pool_is_empty(self):
        blood_request = self.make_request(blood_type="A+", component="RBC")
        substitute = self.make_unit("O-", timezone.now() + timedelta(days=1))

        response = self.client.get(f"{LIST_URL}{blood_request.pk}/matches/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual([row["id"] for row in response.data["units"]], [substitute.pk])
        self.assertFalse(response.data["units"][0]["is_identical"])

    def test_donor_cannot_log_or_list_requests(self):
        self.authenticate(self.donor)

        list_response = self.client.get(LIST_URL)
        create_response = self.client.post(
            LIST_URL,
            {"blood_type": "O-", "component": "RBC", "quantity": 1},
            format="json",
        )

        self.assertEqual(list_response.status_code, 403)
        self.assertEqual(create_response.status_code, 403)
        self.assertEqual(BloodRequest.objects.count(), 0)

    def test_unauthenticated_user_cannot_log_or_list_requests(self):
        self.client.credentials()

        list_response = self.client.get(LIST_URL)
        create_response = self.client.post(
            LIST_URL,
            {"blood_type": "O-", "component": "RBC", "quantity": 1},
            format="json",
        )

        self.assertEqual(list_response.status_code, 401)
        self.assertEqual(create_response.status_code, 401)
        self.assertEqual(BloodRequest.objects.count(), 0)
