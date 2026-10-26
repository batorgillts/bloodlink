from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.db import models
from django.db.models.functions import Lower
# Create your models here.


class UserManager(BaseUserManager):
    use_in_migrations = True

    def _create_user(self, email, password, **extra):
        if not email:
            raise ValueError("Email is required")
        user = self.model(email=self.normalize_email(email).lower(), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    # superuser has every permission witout being granted them one by one
    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", User.Role.COORDINATOR)
        return self._create_user(email, password, **extra)


class User(AbstractUser):
    """Sign-in account for donors and coordinators (ER diagram: User)."""

    class Role(models.TextChoices):
        DONOR = "donor", "Donor"
        COORDINATOR = "coordinator", "Coordinator"

    username = None
    email = models.EmailField(unique=True)
    role = models.CharField(max_length=20, choices=Role.choices, default=Role.DONOR)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    class Meta:
        constraints = [
            # No two users share an email, ignoring case (Sprint 2 constraints table).
            models.UniqueConstraint(Lower("email"), name="user_email_unique_ci"),
        ]

    @property
    def is_coordinator(self):
        return self.role == self.Role.COORDINATOR

    def __str__(self):
        return self.email
