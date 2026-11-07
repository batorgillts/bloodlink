from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User

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
