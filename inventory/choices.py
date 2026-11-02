from django.db import models


class BloodType(models.TextChoices):
    A_POS = "A+", "A+"
    A_NEG = "A-", "A-"
    B_POS = "B+", "B+"
    B_NEG = "B-", "B-"
    AB_POS = "AB+", "AB+"
    AB_NEG = "AB-", "AB-"
    O_POS = "O+", "O+"
    O_NEG = "O-", "O-"


class Component(models.TextChoices):
    RED_BLOOD_CELLS = "RBC", "Red Blood Cells"
    PLASMA = "PLASMA", "Plasma"
    PLATELETS = "PLATELETS", "Platelets"
