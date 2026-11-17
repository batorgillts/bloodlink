from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from accounts.models import User
from donors.models import Donation, Donor
from inventory.models import BloodUnit
from request.models import BloodRequest


class DemoSeedTests(TestCase):
    def test_refuses_ordinary_settings(self):
        with self.assertRaises(CommandError):
            call_command("seed_demo", stdout=StringIO())
        self.assertFalse(User.objects.exists())

    @override_settings(BLOODLINK_DEMO=True)
    def test_repeat_preserves_changes_and_creates_useful_scenarios(self):
        call_command("seed_demo", stdout=StringIO())
        counts = [
            model.objects.count() for model in [User, Donor, Donation, BloodUnit, BloodRequest]
        ]
        donor = Donor.objects.get(user__email="donor@example.com")
        donor.phone = "2025550199"
        donor.save()
        call_command("seed_demo", stdout=StringIO())
        self.assertEqual(
            counts,
            [model.objects.count() for model in [User, Donor, Donation, BloodUnit, BloodRequest]],
        )
        donor.refresh_from_db()
        self.assertEqual(donor.phone, "2025550199")
        self.assertEqual(BloodRequest.objects.count(), 3)
        self.assertEqual(BloodUnit.objects.count(), 13)
        self.assertEqual(
            BloodUnit.objects.get(unit_code__endswith="EXPIRED").effective_status, "expired"
        )
        self.assertTrue(donor.user.check_password("abc123456"))
