from django.db import migrations

# Shelf life per component (Sprint 2 data design). Platelets use the
# conservative end of the 5 to 7 day range.
SHELF_LIFE_DAYS = {"RBC": 42, "PLATELETS": 5, "PLASMA": 365}


def seed(apps, schema_editor):
    ShelfLifeRule = apps.get_model("inventory", "ShelfLifeRule")
    for component, days in SHELF_LIFE_DAYS.items():
        ShelfLifeRule.objects.update_or_create(
            component=component, defaults={"shelf_life_days": days}
        )


def unseed(apps, schema_editor):
    apps.get_model("inventory", "ShelfLifeRule").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [("inventory", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]