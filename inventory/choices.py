from django.db import models

from config.choices import BloodType  # noqa: F401  (shared with donors; re-exported here)


class Component(models.TextChoices):
    RED_BLOOD_CELLS = "RBC", "Red Blood Cells"
    PLASMA = "PLASMA", "Plasma"
    PLATELETS = "PLATELETS", "Platelets"
