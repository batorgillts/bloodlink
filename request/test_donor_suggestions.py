
from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User
from config.choices import Component
from donors.models import Donation, DonationIntervalRule, Donor

from .models import BloodRequest

PASSWORD = "TestPassword123"


class DonorSuggestionTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.coordinator = User.objects.create_user(
            "coordinator@example.com", PASSWORD, role=User.Role.COORDINATOR
        )

    def setUp(self):
        self.client = APIClient()
        self.authenticate(self.coordinator)
        self.today = timezone.localdate()

    def authenticate(self, user):
        token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def donor(self, name, blood_type, **overrides):
        email = f"{name.lower().replace(' ', '.')}@example.com"
        user = User.objects.create_user(email, PASSWORD)
        values = {
            "user": user,
            "full_name": name,
            "date_of_birth": date(1990, 1, 1),
            "blood_type": blood_type,
            "phone": "2125550100",
        }
        values.update(overrides)
        return Donor.objects.create(**values)

    def donated(self, donor, donation_type, days_ago):
        return Donation.objects.create(
            donor=donor,
            donation_type=DonationIntervalRule.objects.get(donation_type=donation_type),
            donation_date=self.today - timedelta(days=days_ago),
            blood_type=donor.blood_type,
            volume_ml=450,
            recorded_by=self.coordinator,
        )

    def blood_request(self, blood_type="O-", component=Component.RED_BLOOD_CELLS, **extra):
        return BloodRequest.objects.create(
            blood_type=blood_type,
            component=component,
            quantity=2,
            logged_by=self.coordinator,
            **extra,
        )

    def suggestions(self, blood_request):
        return self.client.get(f"/api/requests/{blood_request.pk}/donor-suggestions/")

    def names(self, response):
        return [row["full_name"] for row in response.data["donors"]]

    # AC1: compatible under the component's rules AND eligible for that donation type
    def test_ac1_red_cells_list_compatible_eligible_donors(self):
        request = self.blood_request("A+")
        self.donor("Ana A Pos", "A+")
        self.donor("Omar O Neg", "O-")
        self.donor("Bea B Pos", "B+")  # not compatible with A+ red cells
        res = self.suggestions(request)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.names(res), ["Ana A Pos", "Omar O Neg"])
        self.assertEqual(res.data["donation_type"], "whole_blood")

    def test_ac1_plasma_uses_reversed_abo_rules(self):
        request = self.blood_request("A+", Component.PLASMA)
        self.donor("Abe AB Neg", "AB-")
        self.donor("Ola O Pos", "O+")  # O plasma cannot go to an A recipient
        res = self.suggestions(request)
        self.assertEqual(self.names(res), ["Abe AB Neg"])
        self.assertEqual(res.data["donation_type"], "plasma")

    def test_ac1_platelets_use_platelet_rules(self):
        request = self.blood_request("A+", Component.PLATELETS)
        self.donor("Ama A Neg", "A-")
        self.donor("Oto O Pos", "O+")
        self.donor("Ben B Pos", "B+")
        res = self.suggestions(request)
        self.assertEqual(self.names(res), ["Ama A Neg", "Oto O Pos"])
        self.assertEqual(res.data["donation_type"], "platelets")

    def test_ac1_identical_blood_type_is_listed_first(self):
        request = self.blood_request("A+")
        self.donor("Aaron O Neg", "O-")
        self.donor("Zoe A Pos", "A+")
        res = self.suggestions(request)
        self.assertEqual(self.names(res), ["Zoe A Pos", "Aaron O Neg"])
        self.assertEqual([row["is_identical"] for row in res.data["donors"]], [True, False])

    # AC2: next eligible date in the future -> excluded
    def test_ac2_donor_not_yet_eligible_is_excluded(self):
        request = self.blood_request("O-")
        recent = self.donor("Recent Donor", "O-")
        self.donated(recent, "whole_blood", days_ago=55)  # whole blood: 56 days
        res = self.suggestions(request)
        self.assertEqual(self.names(res), [])

    def test_ac2_donor_is_eligible_on_the_next_eligible_date_itself(self):
        request = self.blood_request("O-")
        donor = self.donor("Due Today", "O-")
        self.donated(donor, "whole_blood", days_ago=56)
        res = self.suggestions(request)
        self.assertEqual(self.names(res), ["Due Today"])
        self.assertEqual(res.data["donors"][0]["next_eligible_date"], self.today)

    def test_ac2_uses_the_configured_interval_for_the_donation_type(self):
        request = self.blood_request("O-", Component.PLATELETS)
        donor = self.donor("Platelet Donor", "O-")
        self.donated(donor, "platelets", days_ago=10)
        self.assertEqual(self.names(self.suggestions(request)), ["Platelet Donor"])  # 7 days
        DonationIntervalRule.objects.filter(donation_type="platelets").update(min_interval_days=14)
        self.assertEqual(self.names(self.suggestions(request)), [])

    def test_ac2_only_the_requested_donation_type_sets_eligibility(self):
        # Same rule as US-04: each donation type has its own interval.
        request = self.blood_request("O-", Component.PLASMA)
        donor = self.donor("Gave Whole Blood", "O-")
        self.donated(donor, "whole_blood", days_ago=5)
        self.assertEqual(self.names(self.suggestions(request)), ["Gave Whole Blood"])

    # AC3: each entry shows name, blood type, last donation date and contact information
    def test_ac3_entry_shows_name_blood_type_last_donation_and_contact(self):
        request = self.blood_request("O-")
        donor = self.donor("Maya Patel", "O-", phone="6465550123")
        self.donated(donor, "whole_blood", days_ago=90)
        self.donated(donor, "plasma", days_ago=40)  # most recent donation of any type
        row = self.suggestions(request).data["donors"][0]
        self.assertEqual(row["full_name"], "Maya Patel")
        self.assertEqual(row["blood_type"], "O-")
        self.assertEqual(row["last_donation_date"], self.today - timedelta(days=40))
        self.assertEqual(row["email"], "maya.patel@example.com")
        self.assertEqual(row["phone"], "6465550123")

    def test_ac3_donor_who_never_donated_has_no_last_donation_date(self):
        request = self.blood_request("O-")
        self.donor("First Timer", "O-")
        row = self.suggestions(request).data["donors"][0]
        self.assertIsNone(row["last_donation_date"])

    # AC4: nobody eligible -> "No eligible donors found."
    def test_ac4_no_eligible_donors_shows_message(self):
        request = self.blood_request("O-")
        self.donor("Wrong Type", "A+")
        res = self.suggestions(request)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["donors"], [])
        self.assertEqual(res.data["message"], "No eligible donors found.")

    def test_message_is_empty_when_donors_are_found(self):
        request = self.blood_request("O-")
        self.donor("Someone", "O-")
        self.assertEqual(self.suggestions(request).data["message"], "")

    # AC5 / NFR-5: donors are denied
    def test_ac5_donor_is_denied(self):
        request = self.blood_request("O-")
        donor = self.donor("Signed In Donor", "O-")
        self.authenticate(donor.user)
        self.assertEqual(self.suggestions(request).status_code, 403)

    def test_no_token_returns_401(self):
        request = self.blood_request("O-")
        self.client.credentials()
        self.assertEqual(self.suggestions(request).status_code, 401)

    # Edge cases
    def test_unknown_request_returns_404(self):
        res = self.client.get("/api/requests/99999/donor-suggestions/")
        self.assertEqual(res.status_code, 404)

    def test_withdrawn_and_deleted_donors_are_not_suggested(self):
        request = self.blood_request("O-")
        self.donor("Still Active", "O-")
        self.donor("Withdrew", "O-", status=Donor.Status.WITHDRAWN)
        self.donor("Deleted", "O-", status=Donor.Status.DELETED)
        self.assertEqual(self.names(self.suggestions(request)), ["Still Active"])

    def test_partially_fulfilled_request_still_gets_suggestions(self):
        request = self.blood_request("O-", status=BloodRequest.Status.PARTIALLY_FULFILLED)
        self.donor("Helper", "O-")
        self.assertEqual(self.names(self.suggestions(request)), ["Helper"])

    def test_closed_requests_return_409(self):
        self.donor("Helper", "O-")
        for status in (BloodRequest.Status.FULFILLED, BloodRequest.Status.CANCELLED):
            with self.subTest(status=status):
                request = self.blood_request("O-", status=status)
                self.assertEqual(self.suggestions(request).status_code, 409)
