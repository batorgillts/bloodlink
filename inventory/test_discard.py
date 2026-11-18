"""US-17: discard an unusable blood unit. Test names start with the criterion they prove."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from request.models import BloodRequest, RequestEvent, Reservation

from .models import BloodUnit

PASSWORD = "TestPassword123"
REASON_REQUIRED = "A discard reason is required."


def discard_url(unit):
    return f"/api/units/{unit.pk}/discard/"


class DiscardUnitTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.coordinator = User.objects.create_user(
            "coordinator@example.com", PASSWORD, role=User.Role.COORDINATOR
        )
        cls.donor = User.objects.create_user("donor@example.com", PASSWORD)

    def setUp(self):
        self.client = APIClient()
        self.authenticate(self.coordinator)
        self.now = timezone.now()

    def authenticate(self, user):
        token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def unit(self, code="U-1", **overrides):
        values = {
            "unit_code": code,
            "blood_type": "O-",
            "component": "RBC",
            "collected_at": self.now - timedelta(days=1),
            "created_by": self.coordinator,
        }
        values.update(overrides)
        return BloodUnit.objects.create(**values)

    def blood_request(self, status=BloodRequest.Status.PENDING, quantity=2, **overrides):
        return BloodRequest.objects.create(
            blood_type=overrides.get("blood_type", "O-"),
            component=overrides.get("component", "RBC"),
            quantity=quantity,
            status=status,
            logged_by=self.coordinator,
        )

    def reserved_unit(self, blood_request, code):
        unit = self.unit(code, status=BloodUnit.Status.RESERVED)
        Reservation.objects.create(request=blood_request, unit=unit, reserved_by=self.coordinator)
        return unit

    def discard(self, unit, reason="damaged", **extra):
        data = {"reason": reason, **extra}
        return self.client.post(discard_url(unit), data, format="json")

    def test_ac1_available_unit_is_discarded_with_each_reason(self):
        for reason in ("expired", "damaged", "failed_testing", "other"):
            with self.subTest(reason=reason):
                unit = self.unit(f"AC1-{reason}")
                res = self.discard(unit, reason)
                self.assertEqual(res.status_code, 200)
                unit.refresh_from_db()
                self.assertEqual(unit.status, BloodUnit.Status.DISCARDED)
                self.assertEqual(unit.discard_reason, reason)
                # Wastage is recorded with who and when.
                self.assertEqual(unit.discarded_by, self.coordinator)
                self.assertIsNotNone(unit.discarded_at)
                self.assertIsNone(res.data["request"])
                self.assertFalse(res.data["unit"]["can_discard"])

    def test_ac1_reason_label_from_the_ui_is_accepted(self):
        unit = self.unit()
        res = self.discard(unit, "Failed testing")
        self.assertEqual(res.status_code, 200)
        unit.refresh_from_db()
        self.assertEqual(unit.discard_reason, BloodUnit.DiscardReason.FAILED_TESTING)

    def test_ac2_discarded_unit_is_not_in_available_inventory(self):
        kept = self.unit("KEEP")
        gone = self.unit("GONE")
        self.discard(gone)
        res = self.client.get("/api/units/?status=available")
        codes = [row["unit_code"] for row in res.data]
        self.assertIn(kept.unit_code, codes)
        self.assertNotIn(gone.unit_code, codes)
        discarded = self.client.get("/api/units/?status=discarded")
        self.assertEqual([row["unit_code"] for row in discarded.data], [gone.unit_code])

    def test_ac2_discarded_unit_is_not_matched_to_a_request(self):
        plasma = {"component": "PLASMA", "blood_type": "A+"}
        request = self.blood_request(quantity=1, **plasma)
        kept = self.unit("P-KEEP", **plasma)
        gone = self.unit("P-GONE", **plasma)
        self.discard(gone)
        res = self.client.get(f"/api/requests/{request.pk}/matches/")
        codes = [row["unit_code"] for row in res.data["units"]]
        self.assertEqual(codes, [kept.unit_code])

    def test_ac3_missing_blank_or_null_reason_is_rejected(self):
        unit = self.unit()
        for data in ({}, {"reason": ""}, {"reason": "   "}, {"reason": None}):
            with self.subTest(data=data):
                res = self.client.post(discard_url(unit), data, format="json")
                self.assertEqual(res.status_code, 400)
                self.assertEqual(res.data["reason"], [REASON_REQUIRED])
        unit.refresh_from_db()
        self.assertEqual(unit.status, BloodUnit.Status.AVAILABLE)

    def test_ac3_unknown_reason_is_rejected(self):
        unit = self.unit()
        res = self.discard(unit, "spilled")
        self.assertEqual(res.status_code, 400)
        self.assertIn("Choose one of", res.data["reason"][0])

    def test_ac4_reserved_unit_needs_confirmation_and_names_the_request(self):
        request = self.blood_request(BloodRequest.Status.PARTIALLY_FULFILLED)
        unit = self.reserved_unit(request, "R-1")

        res = self.discard(unit)

        self.assertEqual(res.status_code, 409)
        self.assertEqual(
            res.data["detail"],
            f"This unit is reserved for request {request.pk}. "
            "Discarding it will reduce that request's reserved units.",
        )
        self.assertEqual(res.data["request_id"], request.pk)
        self.assertTrue(res.data["confirm_required"])
        unit.refresh_from_db()
        self.assertEqual(unit.status, BloodUnit.Status.RESERVED)
        self.assertTrue(Reservation.objects.filter(unit=unit, released_at__isnull=True).exists())

    def test_ac4_confirmed_discard_releases_the_reservation(self):
        request = self.blood_request(BloodRequest.Status.PARTIALLY_FULFILLED)
        unit = self.reserved_unit(request, "R-1")

        res = self.discard(unit, confirm=True)

        self.assertEqual(res.status_code, 200)
        unit.refresh_from_db()
        self.assertEqual(unit.status, BloodUnit.Status.DISCARDED)
        reservation = Reservation.objects.get(unit=unit)
        self.assertIsNotNone(reservation.released_at)
        self.assertEqual(reservation.release_reason, Reservation.ReleaseReason.DISCARDED)
        self.assertTrue(
            RequestEvent.objects.filter(
                request=request, event_type=RequestEvent.EventType.RELEASED, unit=unit
            ).exists()
        )

    def test_ac5_request_with_other_reserved_units_becomes_partially_fulfilled(self):
        request = self.blood_request(BloodRequest.Status.FULFILLED, quantity=2)
        first = self.reserved_unit(request, "R-1")
        second = self.reserved_unit(request, "R-2")

        res = self.discard(first, confirm=True)

        self.assertEqual(res.data["request"]["status"], BloodRequest.Status.PARTIALLY_FULFILLED)
        listed = next(r for r in self.client.get("/api/requests/").data if r["id"] == request.pk)
        self.assertEqual(listed["status"], BloodRequest.Status.PARTIALLY_FULFILLED)
        second.refresh_from_db()
        self.assertEqual(second.status, BloodUnit.Status.RESERVED)
        history = self.client.get(f"/api/requests/{request.pk}/history/").data
        change = next(e for e in history if e["event_type"] == "status_changed")
        self.assertEqual(change["from_status"], BloodRequest.Status.FULFILLED)
        self.assertEqual(change["to_status"], BloodRequest.Status.PARTIALLY_FULFILLED)

    def test_ac5_last_reserved_unit_discarded_returns_request_to_pending(self):
        request = self.blood_request(BloodRequest.Status.PARTIALLY_FULFILLED, quantity=2)
        unit = self.reserved_unit(request, "R-1")
        res = self.discard(unit, confirm=True)
        self.assertEqual(res.data["request"]["status"], BloodRequest.Status.PENDING)

    def test_ac6_discarded_unit_does_not_offer_discard_again(self):
        unit = self.unit()
        self.assertTrue(self.client.get(f"/api/units/{unit.pk}/").data["can_discard"])
        self.discard(unit)
        detail = self.client.get(f"/api/units/{unit.pk}/")
        self.assertEqual(detail.data["status"], BloodUnit.Status.DISCARDED)
        self.assertFalse(detail.data["can_discard"])

    def test_ac6_second_discard_is_refused_and_keeps_the_first_record(self):
        unit = self.unit()
        self.discard(unit, "damaged")
        unit.refresh_from_db()
        first_time = unit.discarded_at
        res = self.discard(unit, "other")
        self.assertEqual(res.status_code, 409)
        unit.refresh_from_db()
        self.assertEqual(unit.discard_reason, BloodUnit.DiscardReason.DAMAGED)
        self.assertEqual(unit.discarded_at, first_time)

    def test_ac7_donor_cannot_discard(self):
        unit = self.unit()
        self.authenticate(self.donor)
        res = self.discard(unit)
        self.assertEqual(res.status_code, 403)
        unit.refresh_from_db()
        self.assertEqual(unit.status, BloodUnit.Status.AVAILABLE)

    def test_no_token_returns_401(self):
        unit = self.unit()
        self.client.credentials()
        self.assertEqual(self.discard(unit).status_code, 401)

    def test_unknown_unit_returns_404(self):
        res = self.client.post("/api/units/99999/discard/", {"reason": "damaged"}, format="json")
        self.assertEqual(res.status_code, 404)

    def test_expired_unit_must_use_the_expired_reason(self):
        old = self.unit("OLD", collected_at=self.now - timedelta(days=60))  # RBC: 42 days
        res = self.discard(old, "damaged")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.discard(old, "expired").status_code, 200)

    def test_confirm_is_not_needed_for_an_available_unit(self):
        unit = self.unit()
        self.assertEqual(self.discard(unit, confirm=False).status_code, 200)

    def test_admin_cannot_edit_status_or_discard_fields(self):
        admin_user = User.objects.create_superuser("admin@example.com", PASSWORD)
        unit = self.unit()
        self.client.force_login(admin_user)
        res = self.client.get(f"/admin/inventory/bloodunit/{unit.pk}/change/")
        self.assertEqual(res.status_code, 200)
        for field in ("status", "discard_reason", "discarded_at", "discarded_by"):
            with self.subTest(field=field):
                self.assertNotContains(res, f'name="{field}"')
        self.assertContains(res, 'name="unit_code"')
