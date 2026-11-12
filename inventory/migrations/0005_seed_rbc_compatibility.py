from django.db import migrations


# US-13: RBC ABO/Rh. A unit can serve a recipient only when its antigens are
# acceptable: O is the universal donor, AB+ is the universal recipient, and
# Rh-positive units cannot be given to Rh-negative recipients.
# is_identical is the exact ABO and Rh type, so exact units rank first.
_ABO_RECIPIENTS = {
    "O": ("O", "A", "B", "AB"),
    "A": ("A", "AB"),
    "B": ("B", "AB"),
    "AB": ("AB",),
}
_BLOOD_TYPES = ("O-", "O+", "A-", "A+", "B-", "B+", "AB-", "AB+")


def _compatible(unit_type, request_type):
    unit_abo, unit_rh = unit_type[:-1], unit_type[-1]
    request_abo, request_rh = request_type[:-1], request_type[-1]
    abo_ok = request_abo in _ABO_RECIPIENTS[unit_abo]
    rh_ok = unit_rh == "-" or request_rh == "+"
    return abo_ok and rh_ok


def seed(apps, schema_editor):
    Rule = apps.get_model("inventory", "CompatibilityRule")
    rules = Rule.objects.using(schema_editor.connection.alias)
    for request_type in _BLOOD_TYPES:
        for unit_type in _BLOOD_TYPES:
            if not _compatible(unit_type, request_type):
                continue
            rules.update_or_create(
                component="RBC",
                request_blood_type=request_type,
                unit_blood_type=unit_type,
                defaults={"is_identical": request_type == unit_type},
            )


def unseed(apps, schema_editor):
    Rule = apps.get_model("inventory", "CompatibilityRule")
    Rule.objects.using(schema_editor.connection.alias).filter(component="RBC").delete()


class Migration(migrations.Migration):
    dependencies = [("inventory", "0004_seed_plasma_compatibility")]
    operations = [migrations.RunPython(seed, unseed)]
