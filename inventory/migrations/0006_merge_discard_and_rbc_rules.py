from django.db import migrations


class Migration(migrations.Migration):
    """Join the two 0005 leaves so migrate can apply both after 0004.

    US-17 added 0005_bloodunit_discard_details on develop. US-13 added
    0005_seed_rbc_compatibility on this branch. Both depend on 0004, so Django
    needs one empty merge migration before either can run on a real database.
    """

    dependencies = [
        ("inventory", "0005_bloodunit_discard_details"),
        ("inventory", "0005_seed_rbc_compatibility"),
    ]

    operations = []
