from django.db import migrations


# US-15: team-agreed simplified course-project rules, not a clinical policy.
# Recipient ABO -> allowed platelet unit ABO; Rh is intentionally ignored.
PLATELET_ABO = {
    "O": ("O",),
    "A": ("A", "O"),
    "B": ("B", "O"),
    "AB": ("AB", "A", "B", "O"),
}


def seed(apps, schema_editor):
    Rule = apps.get_model("inventory", "CompatibilityRule")
    rules = Rule.objects.using(schema_editor.connection.alias)
    for recipient, donors in PLATELET_ABO.items():
        for recipient_rh in ("+", "-"):
            for donor in donors:
                for donor_rh in ("+", "-"):
                    rules.update_or_create(
                        component="PLATELETS",
                        request_blood_type=recipient + recipient_rh,
                        unit_blood_type=donor + donor_rh,
                        defaults={"is_identical": recipient == donor},
                    )


def unseed(apps, schema_editor):
    Rule = apps.get_model("inventory", "CompatibilityRule")
    Rule.objects.using(schema_editor.connection.alias).filter(component="PLATELETS").delete()


class Migration(migrations.Migration):
    dependencies = [("inventory", "0006_merge_discard_and_rbc_rules")]
    operations = [migrations.RunPython(seed, unseed)]
