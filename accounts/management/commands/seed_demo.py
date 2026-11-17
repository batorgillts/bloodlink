"""Create repeatable synthetic records only in the isolated local demo."""

from datetime import date, timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from faker import Faker

from accounts.models import User
from donors.models import Donation, DonationIntervalRule, Donor
from inventory.models import BloodUnit
from request.models import BloodRequest, RequestEvent

PASSWORD = "abc123456"
SECONDARY_PASSWORD = "BloodlinkDemo2026!"


class Command(BaseCommand):
    help = "Seed synthetic accounts and inventory using --settings=config.demo_settings."

    @transaction.atomic
    def handle(self, *args, **options):
        if not getattr(settings, "BLOODLINK_DEMO", False):
            raise CommandError(
                "Use --settings=config.demo_settings; ordinary data is not modified."
            )
        fake = Faker("en_US")
        fake.seed_instance(7)

        def account(email, role, password=PASSWORD):
            user, created = User.objects.get_or_create(email=email, defaults={"role": role})
            if created:
                user.set_password(password)
                user.save(update_fields=["password"])
            return user, created

        coordinator, _ = account("coordinator@example.com", User.Role.COORDINATOR)
        today = timezone.localdate()
        now = timezone.now()
        for index, blood_type in enumerate(["A+", "O-", "AB+", "B+", "A-"]):
            email = "donor@example.com" if index == 0 else f"donor{index}@bloodlink.example"
            user, _ = account(
                email, User.Role.DONOR, PASSWORD if index == 0 else SECONDARY_PASSWORD
            )
            donor, created = Donor.objects.get_or_create(
                user=user,
                defaults={
                    "full_name": fake.name(),
                    "date_of_birth": date(1998 + index, 5, 12),
                    "blood_type": blood_type,
                    "phone": f"20255501{index:02d}",
                },
            )
            if created and index == 0:
                Donation.objects.create(
                    donor=donor,
                    donation_type=DonationIntervalRule.objects.get(donation_type="plasma"),
                    donation_date=today - timedelta(days=3),
                    blood_type=blood_type,
                    volume_ml=600,
                    recorded_by=coordinator,
                )

        # A daily batch stays useful when the class presentation is on a later date.
        # Existing units and their reservations/discards are never reset.
        for component in ["RBC", "PLASMA", "PLATELETS"]:
            for index, blood_type in enumerate(["A+", "O-", "AB+", "B+"]):
                BloodUnit.objects.get_or_create(
                    unit_code=f"DEMO-{today:%m%d%y}-{component}-{index}",
                    defaults={
                        "blood_type": blood_type,
                        "component": component,
                        "collected_at": now - timedelta(days=1),
                        "created_by": coordinator,
                    },
                )
        BloodUnit.objects.get_or_create(
            unit_code=f"DEMO-{today:%m%d%y}-EXPIRED",
            defaults={
                "blood_type": "A+",
                "component": "RBC",
                "collected_at": now - timedelta(days=60),
                "created_by": coordinator,
            },
        )
        if not BloodRequest.objects.filter(logged_by=coordinator).exists():
            for component in ["RBC", "PLASMA", "PLATELETS"]:
                request = BloodRequest.objects.create(
                    blood_type="A+",
                    component=component,
                    quantity=2,
                    logged_by=coordinator,
                )
                RequestEvent.objects.create(
                    request=request,
                    event_type=RequestEvent.EventType.LOGGED,
                    to_status=request.status,
                    actor=coordinator,
                )
        self.stdout.write(
            self.style.SUCCESS("Synthetic demo data ready; existing records preserved.")
        )
        self.stdout.write("New accounts: coordinator@example.com / donor@example.com")
        self.stdout.write(f"Initial local-demo password: {PASSWORD}")
