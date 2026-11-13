import threading
from datetime import timedelta
from unittest import skipUnless

from django.db import connection
from django.test import TestCase, TransactionTestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from config.exceptions import Conflict
from inventory.models import BloodUnit

from . import services
from .models import BloodRequest, RequestEvent, Reservation

PASSWORD = "TestPassword123"


def make_unit(code, coordinator, blood_type="O-", component="RBC", days_ago=1, **extra):
    return BloodUnit.objects.create(
        unit_code=code,
        blood_type=blood_type,
        component=component,
        collected_at=timezone.now() - timedelta(days=days_ago),
        created_by=coordinator,
        **extra,
    )


def make_request(coordinator, blood_type="A+", component="RBC", quantity=2):
    return BloodRequest.objects.create(
        logged_by=coordinator, blood_type=blood_type, component=component, quantity=quantity
    )


class ReserveUnitsApiTests(TestCase):
    """US-16: reserve matched units for a blood request."""

    @classmethod
    def setUpTestData(cls):
        cls.coordinator = User.objects.create_user(
            "coordinator@example.com", PASSWORD, role=User.Role.COORDINATOR
        )
        cls.donor = User.objects.create_user("donor@example.com", PASSWORD)

    def setUp(self):
        self.client = APIClient()
        self.authenticate(self.coordinator)
        self.request = make_request(self.coordinator, quantity=2)
        self.unit_a = make_unit("U-A", self.coordinator, blood_type="A+")
        self.unit_b = make_unit("U-B", self.coordinator, blood_type="O-")
        self.unit_c = make_unit("U-C", self.coordinator, blood_type="O+")

    def authenticate(self, user):
        token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def reserve(self, unit_ids, request_id=None):
        request_id = request_id or self.request.pk
        return self.client.post(
            f"/api/requests/{request_id}/reserve/", {"unit_ids": unit_ids}, format="json"
        )

    def test_ac1_reserving_full_quantity_fulfils_request(self):
        res = self.reserve([self.unit_a.pk, self.unit_b.pk])
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["status"], "fulfilled")
        self.assertEqual(res.data["remaining_quantity"], 0)
        self.assertEqual(set(res.data["reserved_units"]), {"U-A", "U-B"})
        for unit in (self.unit_a, self.unit_b):
            unit.refresh_from_db()
            self.assertEqual(unit.status, BloodUnit.Status.RESERVED)
        self.assertEqual(Reservation.objects.filter(request=self.request).count(), 2)

    def test_ac1_reserved_units_leave_available_stock(self):
        self.reserve([self.unit_a.pk])
        self.assertFalse(BloodUnit.objects.usable().filter(pk=self.unit_a.pk).exists())

    def test_ac2_fewer_units_is_partially_fulfilled(self):
        res = self.reserve([self.unit_a.pk])
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["status"], "partially_fulfilled")
        self.assertEqual(res.data["remaining_quantity"], 1)

    def test_ac2_second_reservation_completes_the_request(self):
        self.reserve([self.unit_a.pk])
        res = self.reserve([self.unit_b.pk])
        self.assertEqual(res.data["status"], "fulfilled")

    def test_ac3_more_units_than_requested_returns_400(self):
        res = self.reserve([self.unit_a.pk, self.unit_b.pk, self.unit_c.pk])
        self.assertEqual(res.status_code, 400)
        self.assertIn("exceed requested quantity", str(res.data))
        self.assertFalse(Reservation.objects.exists())

    def test_ac3_counts_units_already_reserved(self):
        self.reserve([self.unit_a.pk])
        res = self.reserve([self.unit_b.pk, self.unit_c.pk])
        self.assertEqual(res.status_code, 400)
        self.assertEqual(Reservation.objects.count(), 1)

    def test_ac4_unit_already_reserved_returns_409(self):
        other = make_request(self.coordinator, quantity=1)
        self.reserve([self.unit_b.pk], request_id=other.pk)
        res = self.reserve([self.unit_b.pk])
        self.assertEqual(res.status_code, 409)
        self.assertIn("no longer available", str(res.data))
        self.assertEqual(Reservation.objects.filter(unit=self.unit_b).count(), 1)

    def test_all_or_nothing_when_one_unit_is_unavailable(self):
        self.unit_b.status = BloodUnit.Status.DISCARDED
        self.unit_b.discard_reason = BloodUnit.DiscardReason.DAMAGED
        self.unit_b.save()
        res = self.reserve([self.unit_a.pk, self.unit_b.pk])
        self.assertEqual(res.status_code, 409)
        self.unit_a.refresh_from_db()
        self.assertEqual(self.unit_a.status, BloodUnit.Status.AVAILABLE)
        self.assertFalse(Reservation.objects.exists())

    def test_expired_unit_returns_409(self):
        old = make_unit("U-OLD", self.coordinator, blood_type="A+", days_ago=50)
        self.assertEqual(self.reserve([old.pk]).status_code, 409)

    def test_incompatible_unit_returns_400(self):
        b_pos = make_unit("U-BPOS", self.coordinator, blood_type="B+")
        res = self.reserve([b_pos.pk])
        self.assertEqual(res.status_code, 400)
        self.assertIn("not compatible", str(res.data))

    def test_wrong_component_returns_400(self):
        plasma = make_unit("U-PL", self.coordinator, blood_type="A+", component="PLASMA")
        self.assertEqual(self.reserve([plasma.pk]).status_code, 400)

    def test_duplicate_and_empty_selection_return_400(self):
        self.assertEqual(self.reserve([self.unit_a.pk, self.unit_a.pk]).status_code, 400)
        self.assertEqual(self.reserve([]).status_code, 400)

    def test_unknown_unit_and_request_return_404(self):
        self.assertEqual(self.reserve([999999]).status_code, 404)
        self.assertEqual(self.reserve([self.unit_a.pk], request_id=999999).status_code, 404)

    def test_fulfilled_or_cancelled_request_returns_409(self):
        for status in (BloodRequest.Status.FULFILLED, BloodRequest.Status.CANCELLED):
            closed = make_request(self.coordinator, quantity=1)
            closed.status = status
            closed.save()
            self.assertEqual(self.reserve([self.unit_a.pk], request_id=closed.pk).status_code, 409)

    def test_history_records_reservations_and_status_change(self):
        self.reserve([self.unit_a.pk, self.unit_b.pk])
        events = RequestEvent.objects.filter(request=self.request)
        self.assertEqual(events.filter(event_type="reserved").count(), 2)
        change = events.get(event_type="status_changed")
        self.assertEqual((change.from_status, change.to_status), ("pending", "fulfilled"))

    def test_ac5_donor_gets_403(self):
        self.authenticate(self.donor)
        self.assertEqual(self.reserve([self.unit_a.pk]).status_code, 403)
        self.assertFalse(Reservation.objects.exists())

    def test_unauthenticated_gets_401(self):
        self.client.credentials()
        self.assertEqual(self.reserve([self.unit_a.pk]).status_code, 401)


@skipUnless(connection.vendor == "postgresql", "Row locks need PostgreSQL (CI uses it).")
class ConcurrentReservationTests(TransactionTestCase):
    """AC4 / NFR: two coordinators reserving the same unit at once, exactly one wins."""

    def test_only_one_of_two_simultaneous_reservations_succeeds(self):
        coordinator = User.objects.create_user(
            "coordinator@example.com", PASSWORD, role=User.Role.COORDINATOR
        )
        unit = make_unit("U-LAST", coordinator, blood_type="O-")
        requests = [make_request(coordinator, quantity=1) for _ in range(2)]
        start = threading.Barrier(2)
        results = []

        def attempt(blood_request):
            try:
                start.wait()
                services.reserve_units(blood_request.pk, [unit.pk], coordinator)
                results.append("reserved")
            except Conflict:
                results.append("conflict")
            finally:
                connection.close()

        threads = [threading.Thread(target=attempt, args=(r,)) for r in requests]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(sorted(results), ["conflict", "reserved"])
        self.assertEqual(Reservation.objects.filter(unit=unit, released_at__isnull=True).count(), 1)
        unit.refresh_from_db()
        self.assertEqual(unit.status, BloodUnit.Status.RESERVED)
