from datetime import date, timedelta
from unittest.mock import patch

from django.db import IntegrityError, transaction
from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from donors.models import Donor

from .calculator import calculate_eligibility
from .models import Donation, DonationIntervalRule
from .services import NO_HISTORY_MESSAGE

URL = "/api/donors/me/eligibility/"
PASSWORD = "TestPassword123"
# 8 weeks, 8 weeks, 16 weeks, 7 days, 4 weeks. See the seed migration for citations.
EXPECTED_INTERVALS = {
    "whole_blood": 56,
    "red_blood_cells": 56,
    "double_red_cells": 112,
    "platelets": 7,
    "plasma": 28,
}


def donate(donor, coordinator, code, on, **extra):
    rule = DonationIntervalRule.objects.get(donation_type=code)
    return Donation.objects.create(
        donor=donor,
        donation_type=rule,
        donation_date=on,
        blood_type=extra.get("blood_type", donor.blood_type),
        volume_ml=extra.get("volume_ml", 450),
        recorded_by=coordinator,
    )


class EligibilityCalculatorTests(SimpleTestCase):
    """The interval formula, with no database and no HTTP."""

    def test_latest_donation_of_that_type_plus_the_interval(self):
        today = date(2026, 10, 28)
        results = calculate_eligibility(
            rules=[("whole_blood", 56), ("platelets", 7)],
            donations=[
                ("whole_blood", date(2026, 1, 1)),
                ("whole_blood", date(2026, 8, 1)),
                ("platelets", date(2026, 10, 25)),
            ],
            today=today,
        )
        whole, platelets = results
        # August 1 + 56 days is September 26, which is already past on October 28.
        self.assertEqual(whole["last_donation_date"], date(2026, 8, 1))
        self.assertEqual(whole["next_eligible_date"], date(2026, 9, 26))
        self.assertTrue(whole["eligible"])
        self.assertEqual(platelets["next_eligible_date"], date(2026, 11, 1))
        self.assertFalse(platelets["eligible"])

    def test_eligible_on_the_next_eligible_date_itself(self):
        today = date(2026, 10, 28)
        on_the_day = calculate_eligibility(
            rules=[("whole_blood", 56)],
            donations=[("whole_blood", today - timedelta(days=56))],
            today=today,
        )[0]
        one_day_early = calculate_eligibility(
            rules=[("whole_blood", 56)],
            donations=[("whole_blood", today - timedelta(days=55))],
            today=today,
        )[0]
        self.assertEqual(on_the_day["next_eligible_date"], today)
        self.assertTrue(on_the_day["eligible"])
        self.assertEqual(one_day_early["next_eligible_date"], today + timedelta(days=1))
        self.assertFalse(one_day_early["eligible"])

    def test_no_donation_of_a_type_is_eligible_today(self):
        today = date(2026, 10, 28)
        row = calculate_eligibility(
            rules=[("plasma", 28)],
            donations=[("platelets", today)],
            today=today,
        )[0]
        self.assertIsNone(row["last_donation_date"])
        self.assertEqual(row["next_eligible_date"], today)
        self.assertTrue(row["eligible"])

    def test_rule_order_is_preserved(self):
        rows = calculate_eligibility(
            rules=[("plasma", 28), ("platelets", 7)],
            donations=[],
            today=date(2026, 10, 28),
        )
        self.assertEqual([row["donation_type"] for row in rows], ["plasma", "platelets"])


class EligibilityApiTests(TestCase):
    """US-04 AC1-AC4, plus the Sprint 2 permission and validation contract."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("alice@example.com", PASSWORD)
        cls.other = User.objects.create_user("bob@example.com", PASSWORD)
        cls.coordinator = User.objects.create_user(
            "coord@example.com", PASSWORD, role=User.Role.COORDINATOR
        )
        cls.donor = Donor.objects.create(
            user=cls.user,
            full_name="Alice Demo",
            date_of_birth=date(1995, 5, 20),
            blood_type="O+",
            phone="2125550100",
        )
        cls.other_donor = Donor.objects.create(
            user=cls.other,
            full_name="Secret Other",
            date_of_birth=date(1996, 4, 10),
            blood_type="AB-",
            phone="9998887777",
        )

    def setUp(self):
        self.client = APIClient()
        self.today = date(2026, 10, 28)
        patcher = patch("donors.services.bank_today", return_value=self.today)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.authenticate(self.user)

    def authenticate(self, user):
        token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def eligibility(self, body):
        return {row["donation_type"]: row for row in body["eligibility"]}

    # The seeded table is the configured rule. These numbers are the regulation.
    def test_seeded_intervals_match_the_regulation(self):
        stored = {
            rule.donation_type: rule.min_interval_days
            for rule in DonationIntervalRule.objects.order_by("id")
        }
        self.assertEqual(stored, EXPECTED_INTERVALS)

    # AC1: history, and a next date per type from that type's own interval.
    def test_history_and_next_date_for_each_type(self):
        donate(self.donor, self.coordinator, "whole_blood", date(2026, 8, 1), volume_ml=450)
        donate(self.donor, self.coordinator, "platelets", date(2026, 10, 25), volume_ml=200)
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["donor_id"], self.donor.pk)
        self.assertEqual(body["as_of"], "2026-10-28")
        self.assertFalse(body["no_donation_history"])
        self.assertIsNone(body["message"])
        self.assertEqual(
            [(row["donation_type"], row["donation_date"]) for row in body["donations"]],
            [("platelets", "2026-10-25"), ("whole_blood", "2026-08-01")],
        )
        self.assertEqual(body["donations"][1]["blood_type"], "O+")
        self.assertEqual(body["donations"][1]["volume_ml"], 450)
        rows = self.eligibility(body)
        self.assertEqual(rows["whole_blood"]["last_donation_date"], "2026-08-01")
        self.assertEqual(rows["whole_blood"]["next_eligible_date"], "2026-09-26")
        self.assertEqual(rows["whole_blood"]["min_interval_days"], 56)
        self.assertTrue(rows["whole_blood"]["eligible"])
        self.assertEqual(rows["platelets"]["next_eligible_date"], "2026-11-01")
        self.assertFalse(rows["platelets"]["eligible"])
        self.assertIsNone(rows["plasma"]["last_donation_date"])
        self.assertTrue(rows["plasma"]["eligible"])
        self.assertTrue(rows["double_red_cells"]["eligible"])
        self.assertTrue(rows["red_blood_cells"]["eligible"])

    def test_only_the_latest_donation_of_a_type_sets_the_date(self):
        donate(self.donor, self.coordinator, "whole_blood", self.today - timedelta(days=100))
        donate(self.donor, self.coordinator, "whole_blood", self.today - timedelta(days=10))
        rows = self.eligibility(self.client.get(URL).json())
        expected = (self.today - timedelta(days=10) + timedelta(days=56)).isoformat()
        self.assertEqual(rows["whole_blood"]["next_eligible_date"], expected)
        self.assertFalse(rows["whole_blood"]["eligible"])

    def test_another_type_does_not_change_this_type(self):
        donate(self.donor, self.coordinator, "platelets", self.today)
        rows = self.eligibility(self.client.get(URL).json())
        self.assertIsNone(rows["whole_blood"]["last_donation_date"])
        self.assertTrue(rows["whole_blood"]["eligible"])
        self.assertFalse(rows["platelets"]["eligible"])

    def test_changing_the_configured_interval_changes_the_date(self):
        donate(self.donor, self.coordinator, "whole_blood", self.today - timedelta(days=10))
        rule = DonationIntervalRule.objects.get(donation_type="whole_blood")
        rule.min_interval_days = 10
        rule.save(update_fields=["min_interval_days"])
        rows = self.eligibility(self.client.get(URL).json())
        self.assertEqual(rows["whole_blood"]["min_interval_days"], 10)
        self.assertEqual(rows["whole_blood"]["next_eligible_date"], self.today.isoformat())
        self.assertTrue(rows["whole_blood"]["eligible"])

    # AC2: eligible when today is the next eligible date; not eligible the day before.
    def test_eligible_when_today_is_the_next_eligible_date(self):
        donate(self.donor, self.coordinator, "whole_blood", self.today - timedelta(days=56))
        rows = self.eligibility(self.client.get(URL).json())
        self.assertEqual(rows["whole_blood"]["next_eligible_date"], self.today.isoformat())
        self.assertTrue(rows["whole_blood"]["eligible"])

    def test_not_eligible_the_day_before_the_next_eligible_date(self):
        donate(self.donor, self.coordinator, "whole_blood", self.today - timedelta(days=55))
        rows = self.eligibility(self.client.get(URL).json())
        self.assertEqual(
            rows["whole_blood"]["next_eligible_date"],
            (self.today + timedelta(days=1)).isoformat(),
        )
        self.assertFalse(rows["whole_blood"]["eligible"])

    # AC4: nothing recorded, and every configured type is currently eligible.
    def test_no_history_reports_current_eligibility(self):
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertTrue(body["no_donation_history"])
        self.assertEqual(body["message"], NO_HISTORY_MESSAGE)
        self.assertEqual(body["donations"], [])
        self.assertEqual(
            {row["donation_type"]: row["min_interval_days"] for row in body["eligibility"]},
            EXPECTED_INTERVALS,
        )
        for row in body["eligibility"]:
            self.assertIsNone(row["last_donation_date"])
            self.assertEqual(row["next_eligible_date"], self.today.isoformat())
            self.assertTrue(row["eligible"])
            self.assertEqual(row["label"], row["donation_type"].replace("_", " ").title())

    def test_own_donor_id_returns_the_same_payload(self):
        response = self.client.get(f"/api/donors/{self.donor.pk}/eligibility/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["donor_id"], self.donor.pk)
        self.assertTrue(response.json()["no_donation_history"])

    # AC3 / NFR-5: another donor's history is neither returned nor disclosed.
    def test_other_donor_is_denied_without_disclosure(self):
        donate(
            self.other_donor,
            self.coordinator,
            "plasma",
            date(2001, 2, 3),
            blood_type="AB-",
            volume_ml=875,
        )
        response = self.client.get(f"/api/donors/{self.other_donor.pk}/eligibility/")
        self.assertEqual(response.status_code, 403)
        disclosed = str(response.data)
        self.assertNotIn("2001-02-03", disclosed)
        self.assertNotIn("Secret Other", disclosed)
        self.assertNotIn(self.other.email, disclosed)
        self.assertNotIn(self.other_donor.phone, disclosed)
        self.assertNotIn("875", disclosed)
        mine = self.client.get(URL)
        self.assertEqual(mine.status_code, 200)
        self.assertEqual(mine.json()["donations"], [])
        self.authenticate(self.other)
        theirs = self.client.get(URL).json()
        self.assertEqual(theirs["donations"][0]["donation_date"], "2001-02-03")

    def test_unknown_donor_id_is_also_denied(self):
        response = self.client.get("/api/donors/999999/eligibility/")
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("Secret Other", str(response.data))

    def test_me_url_cannot_be_retargeted_by_query_string(self):
        response = self.client.get(URL, {"donor_id": self.other_donor.pk})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["donor_id"], self.donor.pk)

    def test_unauthenticated_request_returns_401(self):
        self.client.credentials()
        self.assertEqual(self.client.get(URL).status_code, 401)
        self.assertEqual(
            self.client.get(f"/api/donors/{self.donor.pk}/eligibility/").status_code, 401
        )

    def test_invalid_token_returns_401(self):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer invalid-token")
        self.assertEqual(self.client.get(URL).status_code, 401)

    def test_deactivated_account_token_returns_401(self):
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        self.assertEqual(self.client.get(URL).status_code, 401)

    def test_withdrawn_or_deleted_profile_is_denied(self):
        donate(self.donor, self.coordinator, "whole_blood", date(2026, 1, 1))
        for status in (Donor.Status.WITHDRAWN, Donor.Status.DELETED):
            self.donor.status = status
            self.donor.save(update_fields=["status"])
            response = self.client.get(URL)
            self.assertEqual(response.status_code, 403)
            self.assertNotIn("2026-01-01", str(response.data))

    def test_missing_profile_returns_404(self):
        self.donor.delete()
        self.assertEqual(self.client.get(URL).status_code, 404)
        self.assertEqual(
            self.client.get(f"/api/donors/{self.other_donor.pk}/eligibility/").status_code,
            404,
        )

    def test_coordinator_reads_a_donor_by_id(self):
        donate(self.donor, self.coordinator, "plasma", date(2026, 10, 1))
        self.authenticate(self.coordinator)
        denied = self.client.get(URL)
        self.assertEqual(denied.status_code, 403)
        response = self.client.get(f"/api/donors/{self.donor.pk}/eligibility/")
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["donor_id"], self.donor.pk)
        self.assertEqual(body["donations"][0]["donation_type"], "plasma")
        missing = self.client.get("/api/donors/999999/eligibility/")
        self.assertEqual(missing.status_code, 404)

    def test_coordinator_can_read_a_withdrawn_donors_history(self):
        donate(self.donor, self.coordinator, "whole_blood", date(2026, 3, 1))
        self.donor.status = Donor.Status.WITHDRAWN
        self.donor.save(update_fields=["status"])
        self.authenticate(self.coordinator)
        response = self.client.get(f"/api/donors/{self.donor.pk}/eligibility/")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["donations"][0]["donation_date"], "2026-03-01")

    def test_registration_token_can_open_an_empty_eligibility_page(self):
        self.client.credentials()
        registered = self.client.post(
            "/api/auth/register/",
            {
                "full_name": "Carol Demo",
                "email": "carol@example.com",
                "password": PASSWORD,
                "date_of_birth": "1990-06-15",
                "blood_type": "B+",
                "phone": "2125550300",
            },
            format="json",
        )
        self.assertEqual(registered.status_code, 201)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {registered.data['access']}")
        response = self.client.get(URL)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["no_donation_history"])
        self.assertEqual(response.json()["message"], NO_HISTORY_MESSAGE)

    def test_write_methods_are_not_supported(self):
        self.assertEqual(self.client.post(URL, {}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(URL).status_code, 405)
        self.assertFalse(Donation.objects.filter(donor=self.donor).exists())


class DonationConstraintTests(TestCase):
    """NFR-3: the database rejects a donation outside the allowed values."""

    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user("donor@example.com", PASSWORD)
        cls.coordinator = User.objects.create_user(
            "coord2@example.com", PASSWORD, role=User.Role.COORDINATOR
        )
        cls.donor = Donor.objects.create(
            user=cls.user,
            full_name="Dana Demo",
            date_of_birth=date(1994, 1, 2),
            blood_type="A+",
            phone="2125550142",
        )

    def test_invalid_blood_type_volume_and_interval_are_rejected(self):
        rule = DonationIntervalRule.objects.get(donation_type="whole_blood")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Donation.objects.create(
                    donor=self.donor,
                    donation_type=rule,
                    donation_date=date(2026, 1, 1),
                    blood_type="C+",
                    volume_ml=450,
                    recorded_by=self.coordinator,
                )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Donation.objects.create(
                    donor=self.donor,
                    donation_type=rule,
                    donation_date=date(2026, 1, 1),
                    blood_type="A+",
                    volume_ml=0,
                    recorded_by=self.coordinator,
                )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                DonationIntervalRule.objects.create(donation_type="extra", min_interval_days=0)
        self.assertFalse(Donation.objects.exists())
        self.assertFalse(DonationIntervalRule.objects.filter(donation_type="extra").exists())
