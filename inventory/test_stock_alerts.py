"""US-12: low-stock and expiring-soon alerts. Test names start with the criterion."""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User

from .models import BloodUnit, ShelfLifeRule, StockThreshold

PASSWORD = "TestPassword123"
THRESHOLD_MESSAGE = "The low-stock threshold must be a positive whole number."
DASHBOARD = "/api/inventory/dashboard/"
THRESHOLDS = "/api/inventory/thresholds/"


class StockAlertTests(TestCase):
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

    def unit(self, code, blood_type="O-", component="RBC", days_left=30, **extra):
        """A unit that expires `days_left` days from now (RBC shelf life is 42 days)."""
        shelf_life = ShelfLifeRule.objects.get(component=component).shelf_life_days
        return BloodUnit.objects.create(
            unit_code=code,
            blood_type=blood_type,
            component=component,
            collected_at=self.now - timedelta(days=shelf_life - days_left),
            created_by=self.coordinator,
            **extra,
        )

    def set_threshold(self, **data):
        body = {"blood_type": "O-", "component": "RBC", "minimum_units": 3, **data}
        return self.client.put(THRESHOLDS, body, format="json")

    def dashboard(self):
        res = self.client.get(DASHBOARD)
        self.assertEqual(res.status_code, 200)
        return res.data

    def stock_row(self, data, blood_type="O-", component="RBC"):
        rows = data["stock"]
        return next(r for r in rows if (r["blood_type"], r["component"]) == (blood_type, component))

    def expiring_codes(self, data, component="RBC"):
        group = next(g for g in data["expiring_soon"] if g["component"] == component)
        return [u["unit_code"] for u in group["units"]]

    # AC1 thresholds are saved per blood type and component, and used for alerts
    def test_ac1_threshold_is_saved_and_adjusted(self):
        created = self.set_threshold(minimum_units=3)
        self.assertEqual(created.status_code, 201)
        updated = self.set_threshold(minimum_units=5)
        self.assertEqual(updated.status_code, 200)
        threshold = StockThreshold.objects.get(blood_type="O-", component="RBC")
        self.assertEqual(threshold.minimum_units, 5)
        self.assertEqual(threshold.updated_by, self.coordinator)
        listed = self.client.get(THRESHOLDS).data
        self.assertEqual([(t["blood_type"], t["minimum_units"]) for t in listed], [("O-", 5)])

    def test_ac1_types_and_components_have_separate_thresholds_and_windows(self):
        self.set_threshold(blood_type="O-", component="RBC", minimum_units=4)
        self.set_threshold(blood_type="A+", component="RBC", minimum_units=1)
        self.set_threshold(component="PLASMA", minimum_units=2, expiring_soon_days=60)
        data = self.dashboard()
        self.assertEqual(self.stock_row(data, "O-", "RBC")["minimum_units"], 4)
        self.assertEqual(self.stock_row(data, "A+", "RBC")["minimum_units"], 1)
        self.assertEqual(self.stock_row(data, "O-", "PLASMA")["expiring_soon_days"], 60)
        self.assertEqual(self.stock_row(data, "A+", "PLASMA")["expiring_soon_days"], 30)

    def test_ac1_default_window_follows_each_components_shelf_life(self):
        data = self.dashboard()
        windows = {g["component"]: g["window_days"] for g in data["expiring_soon"]}
        self.assertEqual(windows, {"RBC": 7, "PLASMA": 30, "PLATELETS": 2})

    def test_ac1_shows_the_unit_closest_to_expiry_for_each(self):
        self.unit("LATER", days_left=20)
        self.unit("SOONEST", days_left=3)
        row = self.stock_row(self.dashboard())
        self.assertEqual(row["available"], 2)
        self.assertEqual(row["closest_to_expiry"]["unit_code"], "SOONEST")
        self.assertIsNone(self.stock_row(self.dashboard(), "B+")["closest_to_expiry"])

    def test_ac1_clearing_the_override_returns_to_the_component_window(self):
        self.set_threshold(expiring_soon_days=14)
        self.set_threshold(expiring_soon_days=None)
        self.assertEqual(self.stock_row(self.dashboard())["expiring_soon_days"], 7)

    # Below the threshold -> low-stock alert
    def test_ac2_low_stock_alert_when_below_threshold(self):
        self.set_threshold(minimum_units=3)
        self.unit("U-1")
        self.unit("U-2")
        data = self.dashboard()
        self.assertEqual(
            data["low_stock"],
            [{"blood_type": "O-", "component": "RBC", "available": 2, "minimum_units": 3}],
        )
        self.assertTrue(self.stock_row(data)["is_low"])

    def test_ac2_no_alert_at_or_above_the_threshold(self):
        self.set_threshold(minimum_units=2)
        self.unit("U-1")
        self.unit("U-2")
        self.assertEqual(self.dashboard()["low_stock"], [])

    def test_ac2_no_alert_without_a_threshold(self):
        self.assertEqual(self.dashboard()["low_stock"], [])

    def test_ac2_zero_stock_is_low(self):
        self.set_threshold(blood_type="AB-", component="PLATELETS", minimum_units=1)
        alert = self.dashboard()["low_stock"][0]
        self.assertEqual((alert["blood_type"], alert["available"]), ("AB-", 0))

    #units inside the window are listed by component
    def test_ac3_expiring_units_are_listed_by_component(self):
        self.unit("RBC-SOON", days_left=5)
        self.unit("RBC-LATER", days_left=20)
        self.unit("PLT-SOON", component="PLATELETS", days_left=1)
        self.unit("PLASMA-SOON", component="PLASMA", days_left=25)
        data = self.dashboard()
        self.assertEqual(self.expiring_codes(data, "RBC"), ["RBC-SOON"])
        self.assertEqual(self.expiring_codes(data, "PLATELETS"), ["PLT-SOON"])
        self.assertEqual(self.expiring_codes(data, "PLASMA"), ["PLASMA-SOON"])

    def test_ac3_report_is_ordered_by_expiry(self):
        self.unit("SECOND", days_left=6)
        self.unit("FIRST", days_left=2, blood_type="A+")
        self.assertEqual(self.expiring_codes(self.dashboard()), ["FIRST", "SECOND"])

    def test_ac3_a_threshold_window_overrides_the_component_default(self):
        self.unit("TEN-DAYS", days_left=10)
        self.assertEqual(self.expiring_codes(self.dashboard()), [])
        self.set_threshold(expiring_soon_days=14)
        self.assertEqual(self.expiring_codes(self.dashboard()), ["TEN-DAYS"])

    # AC4: reserved, discarded or expired units drop off on refresh
    def test_ac4_reserved_discarded_and_expired_units_clear_their_reminders(self):
        self.set_threshold(minimum_units=1)
        reserved = self.unit("RES", days_left=3)
        discarded = self.unit("DIS", days_left=3)
        self.unit("GONE", days_left=-1)  # already past expiry
        self.assertEqual(self.expiring_codes(self.dashboard()), ["RES", "DIS"])

        BloodUnit.objects.filter(pk=reserved.pk).update(status=BloodUnit.Status.RESERVED)
        url = f"/api/units/{discarded.pk}/discard/"
        res = self.client.post(url, {"reason": "damaged"}, format="json")
        self.assertEqual(res.status_code, 200)

        data = self.dashboard()
        self.assertEqual(self.expiring_codes(data), [])
        self.assertEqual(self.stock_row(data)["available"], 0)
        self.assertEqual(data["low_stock"][0]["available"], 0)  # low-stock now shows

    # AC5: a threshold that is not a positive number is rejected
    def test_ac5_non_positive_or_non_numeric_threshold_is_rejected(self):
        for value in (0, -2, "abc", "", None, 2.5):
            with self.subTest(value=value):
                res = self.set_threshold(minimum_units=value)
                self.assertEqual(res.status_code, 400)
                self.assertEqual(res.data["minimum_units"], [THRESHOLD_MESSAGE])
        self.assertFalse(StockThreshold.objects.exists())

    def test_ac5_missing_threshold_is_rejected(self):
        res = self.client.put(THRESHOLDS, {"blood_type": "O-", "component": "RBC"}, format="json")
        self.assertEqual(res.status_code, 400)
        self.assertEqual(res.data["minimum_units"], [THRESHOLD_MESSAGE])

    def test_rejected_update_keeps_the_saved_threshold(self):
        self.set_threshold(minimum_units=4)
        self.set_threshold(minimum_units=0)
        self.assertEqual(StockThreshold.objects.get().minimum_units, 4)

    # Validation edge cases
    def test_window_must_be_positive_and_shorter_than_shelf_life(self):
        self.assertEqual(self.set_threshold(expiring_soon_days=0).status_code, 400)
        res = self.set_threshold(component="PLATELETS", expiring_soon_days=5)  # shelf life 5 days
        self.assertEqual(res.status_code, 400)
        self.assertIn("5-day shelf life", res.data["expiring_soon_days"][0])
        res = self.set_threshold(component="PLATELETS", expiring_soon_days=4)
        self.assertEqual(res.status_code, 201)

    def test_unknown_blood_type_or_component_is_rejected(self):
        self.assertEqual(self.set_threshold(blood_type="C+").status_code, 400)
        self.assertEqual(self.set_threshold(component="SALIVA").status_code, 400)

    # NFR-5: coordinators only
    def test_donor_cannot_view_dashboard_or_set_thresholds(self):
        self.authenticate(self.donor)
        self.assertEqual(self.client.get(DASHBOARD).status_code, 403)
        self.assertEqual(self.set_threshold().status_code, 403)
        self.assertFalse(StockThreshold.objects.exists())

    def test_no_token_returns_401(self):
        self.client.credentials()
        self.assertEqual(self.client.get(DASHBOARD).status_code, 401)
        self.assertEqual(self.client.get(THRESHOLDS).status_code, 401)

    def test_database_rejects_a_zero_threshold(self):
        from django.db import IntegrityError, transaction

        with self.assertRaises(IntegrityError), transaction.atomic():
            StockThreshold.objects.create(blood_type="O-", component="RBC", minimum_units=0)
