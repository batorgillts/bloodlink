from datetime import datetime, time, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from config.choices import BloodType, Component
from request.models import BloodRequest

FORECAST_URL = "/api/forecast/weekly/"


class WeeklyDemandForecastTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.coordinator = user_model.objects.create_user(
            email="forecast-test@example.com",
            password="ForecastTest2026!",
            role=user_model.Role.COORDINATOR,
        )
        self.client = APIClient()
        self.client.force_authenticate(user=self.coordinator)
        self.current_week = timezone.localdate() - timedelta(days=timezone.localdate().weekday())

    def add_request(
        self,
        *,
        weeks_ago,
        blood_type="A+",
        component="RBC",
        quantity=1,
        status=BloodRequest.Status.PENDING,
    ):
        week_start = self.current_week - timedelta(weeks=weeks_ago)
        logged_at = timezone.make_aware(
            datetime.combine(week_start + timedelta(days=1), time(hour=12))
        )
        request = BloodRequest.objects.create(
            blood_type=blood_type,
            component=component,
            quantity=quantity,
            status=status,
            logged_by=self.coordinator,
        )
        BloodRequest.objects.filter(pk=request.pk).update(logged_at=logged_at)
        return request

    def get_forecast(self):
        response = self.client.get(FORECAST_URL)
        self.assertEqual(response.status_code, 200)
        return response.data

    def result_for(self, payload, blood_type="A+", component="RBC"):
        return next(
            row
            for row in payload["predictions"]
            if row["blood_type"] == blood_type and row["component"] == component
        )

    def test_more_than_twelve_weeks_uses_twelve_and_returns_a_forecast(self):
        for weeks_ago in range(15):
            self.add_request(weeks_ago=weeks_ago, quantity=weeks_ago + 1)

        payload = self.get_forecast()

        self.assertEqual(payload["history_weeks_used"], 12)
        self.assertEqual(payload["history_status"], "ready")
        result = self.result_for(payload)
        self.assertIsNotNone(result["predicted_demand"])
        self.assertEqual(len(result["history"]), 12)

    def test_four_to_twelve_weeks_uses_available_weeks_and_reports_count(self):
        for weeks_ago in range(1, 9):
            self.add_request(weeks_ago=weeks_ago, quantity=weeks_ago + 1)

        payload = self.get_forecast()

        self.assertEqual(payload["history_weeks_used"], 8)
        self.assertEqual(payload["history_status"], "limited_history")
        result = self.result_for(payload)
        self.assertIsNotNone(result["predicted_demand"])
        self.assertEqual(len(result["history"]), 12)
        self.assertTrue(all(point["quantity"] is None for point in result["history"][:4]))

    def test_fewer_than_four_weeks_returns_no_prediction_and_insufficient_status(self):
        for weeks_ago in range(1, 4):
            self.add_request(weeks_ago=weeks_ago, quantity=weeks_ago + 1)

        payload = self.get_forecast()

        self.assertEqual(payload["history_weeks_used"], 3)
        self.assertEqual(payload["history_status"], "insufficient_history")
        self.assertTrue(all(row["predicted_demand"] is None for row in payload["predictions"]))

    def test_response_has_per_type_weekly_totals_and_excludes_cancelled_requests(self):
        # Four completed weeks for O- plasma establish the data-coverage period.
        for weeks_ago in range(1, 5):
            self.add_request(
                weeks_ago=weeks_ago,
                blood_type="O-",
                component="PLASMA",
                quantity=4,
            )
        self.add_request(weeks_ago=1, quantity=2)
        self.add_request(weeks_ago=1, quantity=3)
        self.add_request(
            weeks_ago=1,
            quantity=100,
            status=BloodRequest.Status.CANCELLED,
        )
        self.add_request(weeks_ago=3, blood_type="O-", quantity=6)

        payload = self.get_forecast()

        expected_pairs = {
            (blood_type, component)
            for blood_type in BloodType.values
            for component in Component.values
        }
        actual_pairs = {
            (row["blood_type"], row["component"]) for row in payload["predictions"]
        }
        self.assertEqual(actual_pairs, expected_pairs)
        self.assertEqual(len(payload["predictions"]), 24)
        self.assertTrue(
            all(len(row["history"]) == 12 for row in payload["predictions"])
        )

        a_positive_rbc = self.result_for(payload, "A+", "RBC")
        previous_week = (self.current_week - timedelta(weeks=1)).isoformat()
        totals = {point["week_start"]: point["quantity"] for point in a_positive_rbc["history"]}
        self.assertEqual(totals[previous_week], 5)
        self.assertNotIn(self.current_week.isoformat(), totals)
        self.assertIsNotNone(a_positive_rbc["predicted_demand"])
        self.assertIsNotNone(self.result_for(payload, "O-", "RBC")["predicted_demand"])

    def test_pending_partial_and_fulfilled_count_but_cancelled_does_not(self):
        for weeks_ago in range(1, 6):
            self.add_request(
                weeks_ago=weeks_ago,
                blood_type="O-",
                component="PLASMA",
                quantity=1,
            )

        self.add_request(weeks_ago=1, quantity=2, status=BloodRequest.Status.PENDING)
        self.add_request(
            weeks_ago=1,
            quantity=3,
            status=BloodRequest.Status.PARTIALLY_FULFILLED,
        )
        self.add_request(weeks_ago=1, quantity=4, status=BloodRequest.Status.FULFILLED)
        self.add_request(weeks_ago=1, quantity=100, status=BloodRequest.Status.CANCELLED)

        payload = self.get_forecast()
        result = self.result_for(payload)
        previous_week = (self.current_week - timedelta(weeks=1)).isoformat()
        weekly_totals = {point["week_start"]: point["quantity"] for point in result["history"]}

        self.assertEqual(weekly_totals[previous_week], 9)

    def test_monday_forecasts_current_week_from_four_completed_weeks(self):
        monday = datetime(2025, 1, 6).date()
        self.current_week = monday
        for weeks_ago in range(1, 5):
            self.add_request(weeks_ago=weeks_ago, quantity=10)
        # This current, incomplete week's requests must not enter the training history.
        self.add_request(weeks_ago=0, quantity=100)

        with patch("forecasting.services.timezone.localdate", return_value=monday):
            payload = self.get_forecast()

        result = self.result_for(payload)
        history = result["history"]
        self.assertEqual(payload["week_start"], monday.isoformat())
        self.assertEqual(payload["week_end"], (monday + timedelta(days=6)).isoformat())
        self.assertEqual(payload["history_weeks_used"], 4)
        last_history_week = datetime.fromisoformat(history[-1]["week_start"]).date()
        self.assertEqual(last_history_week + timedelta(weeks=1), monday)
        self.assertEqual([point["quantity"] for point in history[-4:]], [10, 10, 10, 10])
        self.assertEqual(result["predicted_demand"], 10)

    def test_three_completed_weeks_plus_current_partial_week_is_insufficient(self):
        monday = datetime(2025, 1, 6).date()
        self.current_week = monday
        for weeks_ago in range(1, 4):
            self.add_request(weeks_ago=weeks_ago, quantity=10)
        self.add_request(weeks_ago=0, quantity=20)

        with patch("forecasting.services.timezone.localdate", return_value=monday):
            payload = self.get_forecast()

        self.assertEqual(payload["history_weeks_used"], 3)
        self.assertEqual(payload["history_status"], "insufficient_history")
        self.assertTrue(all(row["predicted_demand"] is None for row in payload["predictions"]))
