from django.db import migrations

# US-12: expiring-soon window per component, scaled to its shelf life
# (red cells 42 days -> 7, platelets 5 days -> 2, plasma 365 days -> 30).
EXPIRING_SOON_DAYS = {"RBC": 7, "PLATELETS": 2, "PLASMA": 30}


def seed(apps, schema_editor):
    ShelfLifeRule = apps.get_model("inventory", "ShelfLifeRule")
    for component, days in EXPIRING_SOON_DAYS.items():
        ShelfLifeRule.objects.filter(component=component).update(expiring_soon_days=days)


class Migration(migrations.Migration):
    dependencies = [("inventory", "0009_stock_alerts")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
