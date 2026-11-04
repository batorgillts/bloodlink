"""Rules layer for Authentication & Access. No HTTP code in here."""

from django.db import IntegrityError, transaction
from rest_framework_simplejwt.tokens import RefreshToken

from config.exceptions import Conflict
from donors.models import Donor

from .models import User

DUPLICATE_EMAIL = "An account with this email is already registered."


def create_donor_account(*, full_name, email, password, date_of_birth, blood_type, phone):
    """Create a donor's User and Donor profile together (US-01 and US-08)."""
    if User.objects.filter(email__iexact=email).exists():
        raise Conflict(DUPLICATE_EMAIL)
    try:
        with transaction.atomic():
            user = User.objects.create_user(email=email, password=password, role=User.Role.DONOR)
            donor = Donor.objects.create(
                user=user,
                full_name=full_name,
                date_of_birth=date_of_birth,
                blood_type=blood_type,
                phone=phone,
            )
    except IntegrityError:
        # Someone registered the same email at the same moment (unique constraint).
        raise Conflict(DUPLICATE_EMAIL)
    return user, donor


def register_donor(*, full_name, email, password, date_of_birth, blood_type, phone):
    """US-01: create the donor account, then sign the registering donor in."""
    user, _donor = create_donor_account(
        full_name=full_name,
        email=email,
        password=password,
        date_of_birth=date_of_birth,
        blood_type=blood_type,
        phone=phone,
    )

    # Signs the donor in automatically (US-01): same tokens as /api/auth/token/.
    refresh = RefreshToken.for_user(user)
    return user, {"access": str(refresh.access_token), "refresh": str(refresh)}
