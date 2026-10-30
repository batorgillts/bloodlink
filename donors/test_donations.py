from datetime import date, timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User

from .models import Donation, DonationIntervalRule, Donor

PASSWORD = "TestPassword123"


def url(donor_id):
    return f"/api/donors/{donor_id}/donations/"


class RecordDonationTests(TestCase):

    @classmethod
    def setUpTestData(cls):
        cls.coordinator = User.objects.create_user(
            "coordinator@example.com", PASSWORD, role=User.Role.COORDINATOR
        )
        cls.donor_user = User.objects.create_user("ana@example.com", PASSWORD)
        cls.donor = Donor.objects.create(
            user=cls.donor_user,
            full_name="Ana Lopez",
            date_of_birth=date(1995, 5, 20),
            blood_type="O-",
            phone="2125550100",
        )

    def setUp(self):
        self.client = APIClient()
        self.authenticate(self.coordinator)
        self.today = timezone.localdate()

    def authenticate(self, user):
        token = RefreshToken.for_user(user).access_token
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    def entry(self, **overrides):
        data = {
            "donation_type": "whole_blood",
            "donation_date": self.today.isoformat(),
            "blood_type": "O-",
            "volume_ml": 450,
        }
        return {**data, **overrides}

    def existing(self, donation_type, days_ago):
        return Donation.objects.create(
            donor=self.donor,
            donation_type=DonationIntervalRule.objects.get(donation_type=donation_type),
            donation_date=self.today - timedelta(days=days_ago),
            blood_type="O-",
            volume_ml=450,
            recorded_by=self.coordinator,
        )

    def row(self, response, donation_type):
        return next(r for r in response.data["eligibility"] if r["donation_type"] == donation_type)

    # all required fields -> the entry is saved
    def test_ac1_coordinator_records_a_donation_with_all_fields(self):
        res = self.client.post(url(self.donor.pk), self.entry())
        self.assertEqual(res.status_code, 201)
        donation = Donation.objects.get(donor=self.donor)
        self.assertEqual(donation.donation_type_id, "whole_blood")
        self.assertEqual(donation.donation_date, self.today)
        self.assertEqual(donation.volume_ml, 450)
        # The coordinator comes from the token, never from the request body.
        self.assertEqual(donation.recorded_by, self.coordinator)
        self.assertEqual(res.data["donation"]["donation_id"], donation.pk)

    # The new record appears in the donor's donation history
    def test_ac2_new_entry_appears_in_donation_history(self):
        self.client.post(url(self.donor.pk), self.entry())
        history = self.client.get(f"/api/donors/{self.donor.pk}/eligibility/")
        self.assertEqual(history.status_code, 200)
        self.assertEqual(len(history.data["donations"]), 1)
        self.assertEqual(history.data["donations"][0]["donation_type"], "whole_blood")
        self.assertFalse(history.data["no_donation_history"])

    # The donor's status for that type becomes "not eligible"
    def test_ac3_eligibility_becomes_not_eligible(self):
        before = self.client.get(f"/api/donors/{self.donor.pk}/eligibility/")
        self.assertTrue(self.row(before, "whole_blood")["eligible"])
        res = self.client.post(url(self.donor.pk), self.entry())
        self.assertFalse(self.row(res, "whole_blood")["eligible"])

    # The next eligible date is recalculated for each type
    def test_ac4_next_eligible_date_is_recalculated_for_each_type(self):
        res = self.client.post(url(self.donor.pk), self.entry())
        whole = self.row(res, "whole_blood")
        self.assertEqual(whole["last_donation_date"], self.today.isoformat())
        self.assertEqual(whole["next_eligible_date"], (self.today + timedelta(56)).isoformat())
        # Every configured type is returned; types not donated stay eligible today.
        self.assertEqual(len(res.data["eligibility"]), DonationIntervalRule.objects.count())
        self.assertTrue(self.row(res, "plasma")["eligible"])

    # a missing required field -> required field error, nothing saved
    def test_ac5_each_missing_required_field_is_rejected(self):
        for field in ("donation_type", "donation_date", "blood_type", "volume_ml"):
            with self.subTest(field=field):
                data = {k: v for k, v in self.entry().items() if k != field}
                res = self.client.post(url(self.donor.pk), data)
                self.assertEqual(res.status_code, 400)
                self.assertIn(field, res.data)
        self.assertFalse(Donation.objects.exists())

    # donor not yet eligible -> rejected with an error message
    def test_ac6_not_yet_eligible_is_rejected(self):
        self.existing("whole_blood", days_ago=10)
        res = self.client.post(url(self.donor.pk), self.entry())
        self.assertEqual(res.status_code, 400)
        next_date = (self.today + timedelta(days=46)).isoformat()
        self.assertIn(next_date, res.data["donation_date"][0])
        self.assertEqual(Donation.objects.count(), 1)

    # a future date is rejected
    def test_ac6_future_date_is_rejected(self):
        tomorrow = (self.today + timedelta(days=1)).isoformat()
        res = self.client.post(url(self.donor.pk), self.entry(donation_date=tomorrow))
        self.assertEqual(res.status_code, 400)
        self.assertIn("donation_date", res.data)

    # Edge cases
    def test_accepted_on_the_next_eligible_date_itself(self):
        self.existing("whole_blood", days_ago=56)
        res = self.client.post(url(self.donor.pk), self.entry())
        self.assertEqual(res.status_code, 201)

    def test_same_day_duplicate_is_rejected(self):
        self.existing("whole_blood", days_ago=0)
        res = self.client.post(url(self.donor.pk), self.entry())
        self.assertEqual(res.status_code, 400)

    def test_backdated_entry_too_close_to_a_later_donation_is_rejected(self):
        self.existing("whole_blood", days_ago=0)
        ten_days_earlier = (self.today - timedelta(days=10)).isoformat()
        res = self.client.post(url(self.donor.pk), self.entry(donation_date=ten_days_earlier))
        self.assertEqual(res.status_code, 400)
        self.assertIn("donation_date", res.data)

    def test_other_donation_type_is_not_blocked(self):
        self.existing("whole_blood", days_ago=1)
        res = self.client.post(url(self.donor.pk), self.entry(donation_type="platelets"))
        self.assertEqual(res.status_code, 201)

    def test_unknown_donation_type_is_rejected(self):
        res = self.client.post(url(self.donor.pk), self.entry(donation_type="saliva"))
        self.assertEqual(res.status_code, 400)
        self.assertIn("donation_type", res.data)

    def test_blood_type_must_match_the_donor(self):
        res = self.client.post(url(self.donor.pk), self.entry(blood_type="A+"))
        self.assertEqual(res.status_code, 400)
        self.assertIn("blood_type", res.data)

    def test_volume_must_be_positive(self):
        res = self.client.post(url(self.donor.pk), self.entry(volume_ml=0))
        self.assertEqual(res.status_code, 400)
        self.assertIn("volume_ml", res.data)

    def test_recorded_by_cannot_be_supplied(self):
        res = self.client.post(url(self.donor.pk), self.entry(recorded_by=self.donor_user.pk))
        self.assertEqual(res.status_code, 400)
        self.assertIn("recorded_by", res.data)

    def test_withdrawn_donor_returns_409(self):
        Donor.objects.filter(pk=self.donor.pk).update(status=Donor.Status.WITHDRAWN)
        res = self.client.post(url(self.donor.pk), self.entry())
        self.assertEqual(res.status_code, 409)
        self.assertFalse(Donation.objects.exists())

    def test_unknown_donor_returns_404(self):
        res = self.client.post(url(99999), self.entry())
        self.assertEqual(res.status_code, 404)

    # NFR-1, NFR-5
    def test_donor_cannot_record_a_donation(self):
        self.authenticate(self.donor_user)
        res = self.client.post(url(self.donor.pk), self.entry())
        self.assertEqual(res.status_code, 403)
        self.assertFalse(Donation.objects.exists())

    def test_no_token_returns_401(self):
        self.client.credentials()
        res = self.client.post(url(self.donor.pk), self.entry())
        self.assertEqual(res.status_code, 401)
