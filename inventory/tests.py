from datetime import datetime, timedelta

from django.db import IntegrityError
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User

from .models import BloodUnit

URL = "/api/units/"


# the definition of done requires every acceptance criterion to pass
# including the error and permission cases.
# Each test below names the case it proves:
# expiry per component, the daylight saving case, 409 duplicate,
# 400 future time and bad fields, 401 without sign-in, 403 for a donor,
# filters, and the database constraints.
def make_unit(code, blood_type="O-", component="RBC", days_ago=1, **extra):
    return BloodUnit.objects.create(
        unit_code=code,
        blood_type=blood_type,
        component=component,
        collected_at=timezone.now() - timedelta(days=days_ago),
        **extra,
    )


class RecordBloodUnitTests(TestCase):
    """US-07: record a unit; expiry is calculated from the shelf-life rule."""

    def setUp(self):
        self.client = APIClient()
        self.coordinator = User.objects.create_user(
            "coord@bloodlink.test", "Password123", role=User.Role.COORDINATOR
        )
        self.donor = User.objects.create_user("donor@bloodlink.test", "Password123")
        self.client.force_authenticate(self.coordinator)
        self.collected = timezone.now() - timedelta(hours=2)

    def payload(self, **overrides):
        data = {
            "unit_code": "bl-0001",
            "blood_type": "A+",
            "component": "RBC",
            "collected_at": self.collected.isoformat(),
        }
        data.update(overrides)
        return data

    def test_coordinator_records_unit_with_calculated_expiry(self):
        res = self.client.post(URL, self.payload(), format="json")
        self.assertEqual(res.status_code, 201)
        unit = BloodUnit.objects.get(unit_code="BL-0001")  # normalized to upper case
        self.assertEqual(unit.expires_at, timezone.localtime(self.collected) + timedelta(days=42))
        self.assertEqual(unit.status, "available")
        self.assertEqual(unit.created_by, self.coordinator)

    def test_platelets_expire_after_five_days(self):
        self.client.post(URL, self.payload(component="PLATELETS"), format="json")
        unit = BloodUnit.objects.get()
        self.assertEqual(unit.expires_at, timezone.localtime(self.collected) + timedelta(days=5))

    def test_ac1_oct_1_10am_expires_nov_12_10am(self):
        # AC1 example: the Nov 1 clock change must not shift the expiry time.
        collected = datetime(2026, 10, 1, 10, 0, tzinfo=timezone.get_current_timezone())
        self.client.post(URL, self.payload(collected_at=collected.isoformat()), format="json")
        expires = timezone.localtime(BloodUnit.objects.get().expires_at)
        self.assertEqual(
            (expires.month, expires.day, expires.hour, expires.minute), (11, 12, 10, 0)
        )

    def test_expiry_cannot_be_typed_in(self):
        typed = (timezone.now() + timedelta(days=999)).isoformat()
        self.client.post(URL, self.payload(expires_at=typed), format="json")
        unit = BloodUnit.objects.get()
        self.assertEqual(unit.expires_at, timezone.localtime(self.collected) + timedelta(days=42))

    def test_duplicate_unit_id_returns_409(self):
        self.client.post(URL, self.payload(), format="json")
        res = self.client.post(URL, self.payload(unit_code="BL-0001"), format="json")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(BloodUnit.objects.count(), 1)

    def test_future_collection_time_returns_400(self):
        future = (timezone.now() + timedelta(hours=1)).isoformat()
        res = self.client.post(URL, self.payload(collected_at=future), format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(BloodUnit.objects.count(), 0)

    def test_missing_and_invalid_fields_return_400(self):
        res = self.client.post(URL, {"unit_code": "X1"}, format="json")
        self.assertEqual(res.status_code, 400)
        res = self.client.post(URL, self.payload(blood_type="C+"), format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(BloodUnit.objects.count(), 0)

    def test_unauthenticated_request_returns_401(self):
        self.client.force_authenticate(None)
        self.assertEqual(self.client.get(URL).status_code, 401)
        self.assertEqual(self.client.post(URL, self.payload(), format="json").status_code, 401)

    def test_donor_is_denied_with_403(self):
        self.client.force_authenticate(self.donor)
        self.assertEqual(self.client.get(URL).status_code, 403)
        self.assertEqual(self.client.post(URL, self.payload(), format="json").status_code, 403)
        self.assertEqual(BloodUnit.objects.count(), 0)


class ViewInventoryTests(TestCase):
    """US-07: view inventory with filters; expired units are flagged."""

    def setUp(self):
        self.client = APIClient()
        coordinator = User.objects.create_user(
            "coord@bloodlink.test", "Password123", role=User.Role.COORDINATOR
        )
        self.client.force_authenticate(coordinator)
        make_unit("U1", "O-", "RBC")
        make_unit("U2", "A+", "PLASMA")
        make_unit("OLD", "O-", "RBC", days_ago=50)

    def test_filter_by_blood_type_and_component(self):
        res = self.client.get(URL, {"blood_type": "O-", "component": "RBC"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual({u["unit_code"] for u in res.data}, {"U1", "OLD"})

    def test_unit_past_expiry_shows_as_expired(self):
        res = self.client.get(URL, {"blood_type": "O-"})
        statuses = {u["unit_code"]: u["effective_status"] for u in res.data}
        self.assertEqual(statuses, {"U1": "available", "OLD": "expired"})

    # adding the following tests to ensure that the filtering by status works correctly
    def test_available_filter_excludes_expired_units(self):
        res = self.client.get(URL, {"status": "available"})
        self.assertEqual({u["unit_code"] for u in res.data}, {"U1", "U2"})

    def test_expired_filter_includes_units_past_expiry(self):
        res = self.client.get(URL, {"status": "expired"})
        self.assertEqual({u["unit_code"] for u in res.data}, {"OLD"})

    def test_invalid_filter_returns_400(self):
        self.assertEqual(self.client.get(URL, {"status": "lost"}).status_code, 400)


class UnitDatabaseConstraintTests(TestCase):
    """NFR-3: the database rejects invalid states even if the API is bypassed."""

    def test_invalid_status_is_rejected(self):
        with self.assertRaises(IntegrityError):
            make_unit("BAD", status="lost")

    def test_discarded_unit_requires_a_reason(self):
        with self.assertRaises(IntegrityError):
            make_unit("BAD2", status="discarded")
