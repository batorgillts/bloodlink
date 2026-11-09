from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from inventory.models import BloodUnit

from .models import BloodRequest, RequestEvent, Reservation

LIST_URL = "/api/requests/"
PASSWORD = "TestPassword123"


class BloodRequestCancellationApiTests(TestCase):
    """US-19: coordinator cancellation, reservation release, and request history."""

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

    def create_request(self, status=BloodRequest.Status.PENDING):
        blood_request = BloodRequest.objects.create(
            logged_by=self.coordinator,
            blood_type="O-",
            component="RBC",
            quantity=2,
            status=status,
        )
        RequestEvent.objects.create(
            request=blood_request,
            event_type=RequestEvent.EventType.LOGGED,
            to_status=status,
            actor=self.coordinator,
        )
        return blood_request

    def create_reserved_unit(self, unit_code):
        now = timezone.now()
        return BloodUnit.objects.create(
            unit_code=unit_code,
            blood_type="O-",
            component="RBC",
            collected_at=now - timedelta(days=1),
            status=BloodUnit.Status.RESERVED,
            created_by=self.coordinator,
        )

    def reserve(self, blood_request, unit):
        return Reservation.objects.create(
            request=blood_request,
            unit=unit,
            reserved_by=self.coordinator,
        )

    def cancel(self, blood_request, data=None):
        return self.client.post(
            f"{LIST_URL}{blood_request.pk}/cancel/",
            {"confirm": True} if data is None else data,
            format="json",
        )

    def test_pending_request_exposes_cancel_option(self):
        pending = self.create_request(BloodRequest.Status.PENDING)
        partial = self.create_request(BloodRequest.Status.PARTIALLY_FULFILLED)
        fulfilled = self.create_request(BloodRequest.Status.FULFILLED)
        cancelled = self.create_request(BloodRequest.Status.CANCELLED)

        response = self.client.get(LIST_URL)
        options = {row["id"]: row["can_cancel"] for row in response.data}

        self.assertEqual(response.status_code, 200)
        self.assertTrue(options[pending.pk])
        self.assertTrue(options[partial.pk])
        self.assertFalse(options[fulfilled.pk])
        self.assertFalse(options[cancelled.pk])

    def test_confirmed_cancel_releases_reserved_unit_and_records_history(self):
        blood_request = self.create_request()
        unit = self.create_reserved_unit("US19-PENDING-01")
        reservation = self.reserve(blood_request, unit)

        response = self.cancel(blood_request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], BloodRequest.Status.CANCELLED)
        self.assertFalse(response.data["can_cancel"])
        self.assertEqual(response.data["released_units"], 1)

        blood_request.refresh_from_db()
        unit.refresh_from_db()
        reservation.refresh_from_db()
        self.assertEqual(blood_request.status, BloodRequest.Status.CANCELLED)
        self.assertEqual(unit.status, BloodUnit.Status.AVAILABLE)
        self.assertIsNotNone(reservation.released_at)
        self.assertEqual(reservation.release_reason, Reservation.ReleaseReason.CANCELLED)

        history = self.client.get(f"{LIST_URL}{blood_request.pk}/history/")
        status_change = next(
            event
            for event in history.data
            if event["event_type"] == RequestEvent.EventType.STATUS_CHANGED
        )
        self.assertEqual(status_change["from_status"], BloodRequest.Status.PENDING)
        self.assertEqual(status_change["to_status"], BloodRequest.Status.CANCELLED)
        self.assertEqual(status_change["actor"], self.coordinator.pk)
        self.assertEqual(status_change["actor_email"], self.coordinator.email)
        self.assertEqual(status_change["matched_unit_codes"], [])
        self.assertTrue(status_change["created_at"])
        self.assertTrue(
            any(
                event["event_type"] == RequestEvent.EventType.RELEASED
                and event["unit"] == unit.pk
                for event in history.data
            )
        )
        list_response = self.client.get(LIST_URL)
        listed_request = next(row for row in list_response.data if row["id"] == blood_request.pk)
        self.assertEqual(listed_request["status"], BloodRequest.Status.CANCELLED)
        self.assertFalse(listed_request["can_cancel"])

    def test_partially_fulfilled_cancel_releases_all_active_units(self):
        blood_request = self.create_request(BloodRequest.Status.PARTIALLY_FULFILLED)
        first_unit = self.create_reserved_unit("US19-PARTIAL-01")
        second_unit = self.create_reserved_unit("US19-PARTIAL-02")
        first_reservation = self.reserve(blood_request, first_unit)
        second_reservation = self.reserve(blood_request, second_unit)

        response = self.cancel(blood_request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], BloodRequest.Status.CANCELLED)
        self.assertEqual(response.data["released_units"], 2)
        for unit in (first_unit, second_unit):
            unit.refresh_from_db()
            self.assertEqual(unit.status, BloodUnit.Status.AVAILABLE)
        for reservation in (first_reservation, second_reservation):
            reservation.refresh_from_db()
            self.assertIsNotNone(reservation.released_at)
            self.assertEqual(reservation.release_reason, Reservation.ReleaseReason.CANCELLED)

    def test_cancellation_days_after_reservation_expiry_keeps_unit_expired(self):
        blood_request = self.create_request()
        unit = self.create_reserved_unit("US19-EXPIRED-AFTER-RESERVATION")
        reservation = self.reserve(blood_request, unit)
        expiry_time = reservation.reserved_at + timedelta(days=2)
        cancellation_time = reservation.reserved_at + timedelta(days=5)
        BloodUnit.objects.filter(pk=unit.pk).update(expires_at=expiry_time)

        with patch("request.services.timezone.now", return_value=cancellation_time):
            response = self.cancel(blood_request)

        self.assertEqual(response.status_code, 200)
        self.assertLess(blood_request.logged_at, reservation.reserved_at)
        self.assertLess(reservation.reserved_at, expiry_time)
        self.assertLess(expiry_time, cancellation_time)
        unit.refresh_from_db()
        reservation.refresh_from_db()
        self.assertEqual(unit.status, BloodUnit.Status.EXPIRED)
        self.assertEqual(reservation.released_at, cancellation_time)
        self.assertEqual(reservation.release_reason, Reservation.ReleaseReason.CANCELLED)

    def test_fulfilled_request_cannot_be_cancelled(self):
        blood_request = self.create_request(BloodRequest.Status.FULFILLED)
        unit = self.create_reserved_unit("US19-FULFILLED-01")
        reservation = self.reserve(blood_request, unit)

        response = self.cancel(blood_request)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(
            response.data["detail"],
            "Fulfilled requests cannot be cancelled.",
        )
        blood_request.refresh_from_db()
        unit.refresh_from_db()
        reservation.refresh_from_db()
        self.assertEqual(blood_request.status, BloodRequest.Status.FULFILLED)
        self.assertEqual(unit.status, BloodUnit.Status.RESERVED)
        self.assertIsNone(reservation.released_at)

    def test_cancellation_requires_explicit_confirmation(self):
        blood_request = self.create_request()
        unit = self.create_reserved_unit("US19-UNCONFIRMED-01")
        reservation = self.reserve(blood_request, unit)

        for payload in ({}, {"confirm": False}):
            with self.subTest(payload=payload):
                response = self.cancel(blood_request, payload)
                self.assertEqual(response.status_code, 400)

        blood_request.refresh_from_db()
        unit.refresh_from_db()
        reservation.refresh_from_db()
        self.assertEqual(blood_request.status, BloodRequest.Status.PENDING)
        self.assertEqual(unit.status, BloodUnit.Status.RESERVED)
        self.assertIsNone(reservation.released_at)

    def test_donor_cannot_cancel_or_read_request_history(self):
        blood_request = self.create_request()
        unit = self.create_reserved_unit("US19-DONOR-01")
        reservation = self.reserve(blood_request, unit)
        self.authenticate(self.donor)

        cancel_response = self.cancel(blood_request)
        history_response = self.client.get(f"{LIST_URL}{blood_request.pk}/history/")

        self.assertEqual(cancel_response.status_code, 403)
        self.assertEqual(history_response.status_code, 403)
        blood_request.refresh_from_db()
        unit.refresh_from_db()
        reservation.refresh_from_db()
        self.assertEqual(blood_request.status, BloodRequest.Status.PENDING)
        self.assertEqual(unit.status, BloodUnit.Status.RESERVED)
        self.assertIsNone(reservation.released_at)
