from django.db import migrations


# US-14: recipient ABO -> allowed plasma unit ABO. Rh does not exclude plasma.
PLASMA_ABO = {
    "A": ("A", "AB"),
    "B": ("B", "AB"),
    "AB": ("AB",),
    "O": ("O", "A", "B", "AB"),
}


def seed(apps, schema_editor):
    Rule = apps.get_model("inventory", "CompatibilityRule")
    rules = Rule.objects.using(schema_editor.connection.alias)
    for recipient, donors in PLASMA_ABO.items():
        for recipient_rh in ("+", "-"):
            for donor in donors:
                for donor_rh in ("+", "-"):
                    rules.update_or_create(
                        component="PLASMA",
                        request_blood_type=recipient + recipient_rh,
                        unit_blood_type=donor + donor_rh,
                        defaults={"is_identical": recipient == donor},
                    )


def unseed(apps, schema_editor):
    Rule = apps.get_model("inventory", "CompatibilityRule")
    Rule.objects.using(schema_editor.connection.alias).filter(component="PLASMA").delete()


class Migration(migrations.Migration):
    dependencies = [("inventory", "0003_compatibility_rule")]
    operations = [migrations.RunPython(seed, unseed)]
