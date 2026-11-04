from django.db import models
from config.choices import BloodType

class Component(models.TextChoices):
    RED_BLOOD_CELLS = "RBC", "Red Blood Cells"
    PLASMA = "PLASMA", "Plasma"
    PLATELETS = "PLATELETS", "Platelets"
