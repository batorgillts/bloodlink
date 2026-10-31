from datetime import date

from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from accounts.models import User

from .models import Donation, DonationIntervalRule, Donor

URL = "/api/donors/me/withdraw/"
PASSWORD = "TestPassword123"


class WithdrawRegistrationTests(TestCase):
    """US-05: a donor withdraws their own registration and keeps donation history."""

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
            full_name="Bob Demo",
            date_of_birth=date(1996, 4, 10),
            blood_type="A+",
            phone="2125550200",
        )
        rule = DonationIntervalRule.objects.get(donation_type="whole_blood")
        cls.donation = Donation.objects.create(
            donor=cls.donor,
            donation_type=rule,
            donation_date=date(2026, 3, 1),
            blood_type="O+",
            volume_ml=450,
            recorded_by=cls.coordinator,
        )

    def setUp(self):
        self.client = APIClient()
        self.authenticate(self.user)

    def authenticate(self, user):
        token = RefreshToken.for_user(user)
        self.refresh = str(token)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token.access_token}")

    def withdraw(self, url=URL, body=None):
        if body is None:
            body = {"confirm": True}
        return self.client.post(url, body, format="json")

    # AC1: confirmation deactivates the account and marks the donor withdrawn.
    def test_confirm_withdrawal_deactivates_account(self):
        response = self.withdraw()
        self.user.refresh_from_db()
        self.donor.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(),
            {
                "donor_id": self.donor.pk,
                "status": Donor.Status.WITHDRAWN,
                "account_active": False,
                "donation_history_retained": True,
            },
        )
        self.assertFalse(self.user.is_active)
        self.assertTrue(self.user.check_password(PASSWORD))
        self.assertEqual(self.donor.status, Donor.Status.WITHDRAWN)
        self.assertEqual(self.user.email, "alice@example.com")
        self.assertTrue(Donation.objects.filter(pk=self.donation.pk, donor=self.donor).exists())

    def test_own_donor_id_can_withdraw(self):
        response = self.withdraw(f"/api/donors/{self.donor.pk}/withdraw/")
        self.donor.refresh_from_db()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.donor.status, Donor.Status.WITHDRAWN)

    # AC2: the original email and password can no longer sign in.
    def test_withdrawn_donor_cannot_sign_in(self):
        self.assertEqual(self.withdraw().status_code, 200)
        self.client.credentials()
        response = self.client.post(
            "/api/auth/token/",
            {"email": "alice@example.com", "password": PASSWORD},
            format="json",
        )
        self.assertEqual(response.status_code, 401)
        self.assertNotIn("access", response.data)

    def test_existing_access_and_refresh_tokens_stop_working(self):
        refresh = self.refresh
        self.assertEqual(self.withdraw().status_code, 200)
        contact = self.client.get("/api/donors/me/contact/")
        refreshed = self.client.post(
            "/api/auth/token/refresh/", {"refresh": refresh}, format="json"
        )
        self.assertEqual(contact.status_code, 401)
        self.assertEqual(refreshed.status_code, 401)

    # AC3: coordinator search no longer lists the withdrawn donor.
    def test_withdrawn_donor_is_absent_from_coordinator_search(self):
        self.assertEqual(self.withdraw().status_code, 200)
        self.authenticate(self.coordinator)
        by_email = self.client.get("/api/donors/", {"email": "alice@example.com"})
        by_name = self.client.get("/api/donors/", {"name": "Alice"})
        self.assertEqual(by_email.status_code, 200)
        self.assertEqual(by_email.json(), [])
        self.assertEqual([row["id"] for row in by_name.json()], [])
        self.assertEqual(
            [row["id"] for row in self.client.get("/api/donors/").json()],
            [self.other_donor.pk],
        )

    # AC4: donation history remains visible to a coordinator after withdrawal.
    def test_coordinator_still_sees_donation_history(self):
        self.assertEqual(self.withdraw().status_code, 200)
        self.authenticate(self.coordinator)
        detail = self.client.get(f"/api/donors/{self.donor.pk}/")
        eligibility = self.client.get(f"/api/donors/{self.donor.pk}/eligibility/")
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json()["status"], Donor.Status.WITHDRAWN)
        self.assertEqual(detail.json()["donations"][0]["donation_date"], "2026-03-01")
        self.assertEqual(eligibility.status_code, 200)
        self.assertEqual(eligibility.json()["donations"][0]["donation_id"], self.donation.pk)
        self.assertEqual(Donation.objects.filter(donor=self.donor).count(), 1)

    def test_missing_or_false_confirmation_changes_nothing(self):
        for body in [{}, {"confirm": False}, {"confirm": None}, [], "confirm"]:
            with self.subTest(body=body):
                response = self.client.post(URL, body, format="json")
                self.assertEqual(response.status_code, 400)
                self.user.refresh_from_db()
                self.donor.refresh_from_db()
                self.assertTrue(self.user.is_active)
                self.assertEqual(self.donor.status, Donor.Status.ACTIVE)

    def test_unexpected_fields_are_rejected(self):
        response = self.withdraw(body={"confirm": True, "status": "deleted"})
        self.assertEqual(response.status_code, 400)
        self.donor.refresh_from_db()
        self.assertEqual(self.donor.status, Donor.Status.ACTIVE)

    def test_other_donor_id_is_denied_without_disclosure(self):
        response = self.withdraw(f"/api/donors/{self.other_donor.pk}/withdraw/")
        unknown = self.withdraw("/api/donors/999999/withdraw/")
        self.user.refresh_from_db()
        self.other.refresh_from_db()
        self.donor.refresh_from_db()
        self.other_donor.refresh_from_db()
        self.assertEqual(response.status_code, 403)
        self.assertEqual(unknown.status_code, 403)
        self.assertNotIn("bob@example.com", str(response.data))
        self.assertNotIn("2125550200", str(response.data))
        self.assertTrue(self.user.is_active)
        self.assertTrue(self.other.is_active)
        self.assertEqual(self.donor.status, Donor.Status.ACTIVE)
        self.assertEqual(self.other_donor.status, Donor.Status.ACTIVE)

    def test_coordinator_is_denied(self):
        self.authenticate(self.coordinator)
        response = self.withdraw()
        self.assertEqual(response.status_code, 403)
        self.donor.refresh_from_db()
        self.assertEqual(self.donor.status, Donor.Status.ACTIVE)

    def test_anonymous_request_is_unauthorized(self):
        self.client.credentials()
        self.assertEqual(self.withdraw().status_code, 401)
        self.donor.refresh_from_db()
        self.assertEqual(self.donor.status, Donor.Status.ACTIVE)

    def test_missing_profile_returns_404(self):
        Donation.objects.filter(donor=self.donor).delete()
        self.donor.delete()
        response = self.withdraw()
        self.assertEqual(response.status_code, 404)
        self.user.refresh_from_db()
        self.assertTrue(self.user.is_active)

    def test_withdrawn_or_deleted_profile_cannot_withdraw_again(self):
        for donor_status in (Donor.Status.WITHDRAWN, Donor.Status.DELETED):
            with self.subTest(donor_status=donor_status):
                self.donor.status = donor_status
                self.donor.save(update_fields=["status"])
                self.user.is_active = True
                self.user.save(update_fields=["is_active"])
                self.authenticate(self.user)
                response = self.withdraw()
                self.donor.refresh_from_db()
                self.user.refresh_from_db()
                self.assertEqual(response.status_code, 403)
                self.assertEqual(self.donor.status, donor_status)
                self.assertTrue(self.user.is_active)
                self.assertTrue(Donation.objects.filter(pk=self.donation.pk).exists())

    def test_register_then_withdraw_then_sign_in_fails(self):
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
        withdrawn = self.withdraw()
        self.assertEqual(withdrawn.status_code, 200)
        self.client.credentials()
        sign_in = self.client.post(
            "/api/auth/token/",
            {"email": "carol@example.com", "password": PASSWORD},
            format="json",
        )
        duplicate = self.client.post(
            "/api/auth/register/",
            {
                "full_name": "Carol Again",
                "email": "carol@example.com",
                "password": PASSWORD,
                "date_of_birth": "1990-06-15",
                "blood_type": "B+",
                "phone": "2125550301",
            },
            format="json",
        )
        self.assertEqual(sign_in.status_code, 401)
        self.assertEqual(duplicate.status_code, 409)

    def test_other_methods_are_not_supported(self):
        self.assertEqual(self.client.get(URL).status_code, 405)
        self.assertEqual(self.client.patch(URL, {"confirm": True}, format="json").status_code, 405)
        self.assertEqual(self.client.delete(URL).status_code, 405)
        self.donor.refresh_from_db()
        self.assertEqual(self.donor.status, Donor.Status.ACTIVE)
