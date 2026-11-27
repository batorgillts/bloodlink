"""US-20: request history and audit log."""

from datetime import datetime, timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from inventory.models import BloodUnit

from .models import BloodRequest, RequestEvent

LIST_URL = "/api/requests/history/"
PASSWORD = "TestPassword123"


class RequestHistoryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.coordinator = User.objects.create_user(
            "history-coordinator@example.com",
            PASSWORD,
            role=User.Role.COORDINATOR,
            first_name="Ava",
            last_name="Chen",
        )
        cls.donor = User.objects.create_user("history-donor@example.com", PASSWORD)

    def setUp(self):
        self.client = APIClient()
        self.authenticate(self.coordinator)

    def authenticate(self, user):
        token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def log_request(self, **overrides):
        payload = {"blood_type": "A+", "component": "RBC", "quantity": 2}
        payload.update(overrides)
        response = self.client.post("/api/requests/", payload, format="json")
        self.assertEqual(response.status_code, 201)
        return BloodRequest.objects.get(pk=response.data["id"])

    def stamp(self, blood_request, when):
        blood_request.logged_at = when
        blood_request.save(update_fields=["logged_at"])

    def test_logged_request_shows_details_and_coordinator(self):
        blood_request = self.log_request()
        body = self.client.get(LIST_URL).json()
        row = next(item for item in body["requests"] if item["id"] == blood_request.pk)

        self.assertEqual(row["blood_type"], "A+")
        self.assertEqual(row["component"], "RBC")
        self.assertEqual(row["quantity"], 2)
        self.assertEqual(parse_datetime(row["logged_at"]), blood_request.logged_at)
        self.assertEqual(row["coordinator"], "Ava Chen")
        self.assertEqual(row["logged_by"], self.coordinator.pk)
        logged = row["events"][0]
        self.assertEqual(logged["event_type"], "logged")
        self.assertEqual(logged["actor_name"], "Ava Chen")
        self.assertTrue(logged["created_at"])

    def test_match_reserve_and_status_changes_are_listed_in_order(self):
        blood_request = self.log_request(quantity=1)
        unit = BloodUnit.objects.create(
            unit_code="US20-A",
            blood_type="A+",
            component="RBC",
            collected_at=timezone.now() - timedelta(days=1),
            created_by=self.coordinator,
        )

        match = self.client.get(f"/api/requests/{blood_request.pk}/matches/")
        self.assertEqual(match.status_code, 200)
        self.assertEqual([item["unit_code"] for item in match.data["units"]], ["US20-A"])

        reserved = self.client.post(
            f"/api/requests/{blood_request.pk}/reserve/",
            {"unit_ids": [unit.pk]},
            format="json",
        )
        self.assertEqual(reserved.status_code, 201)

        events = self.client.get(f"/api/requests/{blood_request.pk}/history/").json()
        self.assertEqual(
            [event["event_type"] for event in events],
            ["logged", "matched", "reserved", "status_changed"],
        )
        matched = events[1]
        self.assertEqual(matched["matched_unit_codes"], ["US20-A"])
        self.assertEqual(matched["actor"], self.coordinator.pk)
        self.assertTrue(matched["created_at"])
        self.assertEqual(events[2]["unit"], unit.pk)
        self.assertEqual(events[2]["unit_code"], "US20-A")
        self.assertTrue(events[2]["created_at"])
        self.assertEqual(events[3]["from_status"], "pending")
        self.assertEqual(events[3]["to_status"], "fulfilled")
        self.assertEqual(events[3]["actor_email"], self.coordinator.email)

    def test_date_range_returns_only_requests_logged_in_that_period(self):
        inside = self.log_request()
        outside = self.log_request(blood_type="O-")
        self.stamp(inside, timezone.make_aware(datetime(2026, 11, 2, 15, 0)))
        self.stamp(outside, timezone.make_aware(datetime(2026, 10, 1, 9, 0)))

        response = self.client.get(
            LIST_URL, {"logged_from": "2026-11-01", "logged_to": "2026-11-30"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["message"], "")
        self.assertEqual([row["id"] for row in response.data["requests"]], [inside.pk])

    def test_empty_date_range_uses_the_period_message(self):
        blood_request = self.log_request()
        self.stamp(blood_request, timezone.make_aware(datetime(2026, 11, 2, 15, 0)))

        response = self.client.get(
            LIST_URL, {"logged_from": "2025-01-01", "logged_to": "2025-01-31"}
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["requests"], [])
        self.assertEqual(response.data["message"], "No requests found for this period")

    def test_request_details_can_be_filtered_independently(self):
        original = self.log_request()
        other_type = self.log_request(blood_type="A-")
        other_component = self.log_request(component="PLASMA")
        other_quantity = self.log_request(quantity=3)
        cases = (
            ({"blood_type": "A+"}, [original, other_component, other_quantity]),
            ({"component": "RBC"}, [original, other_type, other_quantity]),
            ({"quantity": 2}, [original, other_type, other_component]),
            ({}, [original, other_type, other_component, other_quantity]),
        )

        for filters, expected in cases:
            with self.subTest(filters=filters):
                response = self.client.get(LIST_URL, filters)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["message"], "")
                self.assertCountEqual(
                    [row["id"] for row in response.data["requests"]],
                    [record.pk for record in expected],
                )

    def test_request_details_and_inclusive_dates_are_combined(self):
        first = self.log_request()
        last = self.log_request()
        self.stamp(first, timezone.make_aware(datetime(2026, 11, 1, 0, 0)))
        self.stamp(last, timezone.make_aware(datetime(2026, 11, 30, 23, 59)))
        for overrides in (
            {"blood_type": "A-"},
            {"component": "PLASMA"},
            {"quantity": 3},
        ):
            nonmatching = self.log_request(**overrides)
            self.stamp(nonmatching, timezone.make_aware(datetime(2026, 11, 15, 12, 0)))
        outside = self.log_request()
        self.stamp(outside, timezone.make_aware(datetime(2026, 12, 1, 0, 0)))

        response = self.client.get(
            LIST_URL,
            {
                "blood_type": "A+",
                "component": "RBC",
                "quantity": 2,
                "logged_from": "2026-11-01",
                "logged_to": "2026-11-30",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertCountEqual(
            [row["id"] for row in response.data["requests"]], [first.pk, last.pk]
        )

    def test_invalid_request_detail_filters_are_rejected(self):
        cases = (
            {"blood_type": "A"},
            {"component": "WHOLE_BLOOD"},
            {"quantity": "0"},
            {"quantity": "-1"},
            {"quantity": "1.5"},
            {"quantity": "two"},
        )
        for filters in cases:
            with self.subTest(filters=filters):
                response = self.client.get(LIST_URL, filters)
                self.assertEqual(response.status_code, 400)
                self.assertIn(next(iter(filters)), response.data)

    def test_empty_detail_filters_use_the_filters_message(self):
        blood_request = self.log_request()
        self.stamp(blood_request, timezone.make_aware(datetime(2026, 11, 2, 15, 0)))
        cases = (
            {"blood_type": "O-"},
            {"component": "PLATELETS"},
            {"quantity": 99},
            {
                "blood_type": "A+",
                "logged_from": "2025-01-01",
                "logged_to": "2025-01-31",
            },
        )
        for filters in cases:
            with self.subTest(filters=filters):
                response = self.client.get(LIST_URL, filters)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.data["requests"], [])
                self.assertEqual(response.data["message"], "No requests match these filters.")

    def test_empty_history_without_filters_has_no_filter_message(self):
        response = self.client.get(LIST_URL)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, {"requests": [], "message": ""})

    def test_invalid_date_range_is_rejected(self):
        reversed_range = self.client.get(
            LIST_URL, {"logged_from": "2026-12-01", "logged_to": "2026-11-01"}
        )
        one_sided = self.client.get(LIST_URL, {"logged_from": "2026-11-01"})
        self.assertEqual(reversed_range.status_code, 400)
        self.assertEqual(one_sided.status_code, 400)

    def test_history_entries_cannot_be_edited_or_deleted(self):
        blood_request = self.log_request()
        event = RequestEvent.objects.get(request=blood_request, event_type="logged")
        detail_url = f"/api/requests/{blood_request.pk}/history/"

        for method in ("put", "patch", "delete"):
            response = getattr(self.client, method)(detail_url, {}, format="json")
            list_response = getattr(self.client, method)(LIST_URL, {}, format="json")
            self.assertEqual(response.status_code, 405)
            self.assertEqual(list_response.status_code, 405)
            self.assertIn("cannot be edited or deleted", response.data["detail"])

        with self.assertRaises(ValidationError):
            event.to_status = "cancelled"
            event.save()
        with self.assertRaises(ValidationError):
            event.delete()
        with self.assertRaises(ValidationError):
            RequestEvent.objects.filter(pk=event.pk).update(to_status="cancelled")
        with self.assertRaises(ValidationError):
            RequestEvent.objects.filter(pk=event.pk).delete()
        event.refresh_from_db()
        self.assertEqual(event.to_status, "pending")

    def test_donor_and_anonymous_cannot_open_request_history(self):
        blood_request = self.log_request()
        detail_url = f"/api/requests/{blood_request.pk}/history/"

        self.authenticate(self.donor)
        self.assertEqual(self.client.get(LIST_URL).status_code, 403)
        self.assertEqual(self.client.get(detail_url).status_code, 403)

        self.client.credentials()
        self.assertEqual(self.client.get(LIST_URL).status_code, 401)
        self.assertEqual(self.client.get(detail_url).status_code, 401)
