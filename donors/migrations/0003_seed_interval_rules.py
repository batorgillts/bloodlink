from django.db import migrations

# Configured intervals (Sprint 2: medical rules live in the table, not in code).
# whole_blood: 56 days — 21 CFR 630.15(a)(1)(i), one Whole Blood unit per 8 weeks.
# red_blood_cells: 56 days — 21 CFR 630.15(a)(1)(i), one apheresis Red Blood Cell unit per 8 weeks.
# double_red_cells: 112 days — 21 CFR 630.15(a)(1)(i), two Red Blood Cell units per 16 weeks.
# platelets: 7 days — 21 CFR 640.21(e)(3), after a plateletpheresis of 6 x 10^11 or more.
# plasma: 28 days — 21 CFR 630.3(e) and 640.32, no plasma in the preceding 4 weeks.

RULES = [
    ("whole_blood", 56),
    ("red_blood_cells", 56),
    ("double_red_cells", 112),
    ("platelets", 7),
    ("plasma", 28),
]


def seed_interval_rules(apps, schema_editor):
    rule = apps.get_model("donors", "DonationIntervalRule")
    rule.objects.bulk_create(
        [
            rule(donation_type=donation_type, min_interval_days=days)
            for donation_type, days in RULES
        ]
    )


def remove_interval_rules(apps, schema_editor):
    rule = apps.get_model("donors", "DonationIntervalRule")
    codes = [donation_type for donation_type, _days in RULES]
    rule.objects.filter(donation_type__in=codes).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("donors", "0002_donationintervalrule_donation"),
    ]

    operations = [
        migrations.RunPython(seed_interval_rules, remove_interval_rules),
    ]
