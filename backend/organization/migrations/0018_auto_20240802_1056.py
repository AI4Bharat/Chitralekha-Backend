from django.db import migrations


def transfer_organization_owner(apps, schema_editor):
    Organization = apps.get_model("organization", "Organization")
    for organization in Organization.objects.all():
        if (
            organization.organization_owner_id
        ):  # Check by ID since the field might be removed in later stages
            organization.organization_owners.add(organization.organization_owner_id)
            organization.save()

class Migration(migrations.Migration):
    dependencies = [
        (
            "organization",
            "0017_organization_organization_owners",
        ),  # replace with your previous migration file
    ]

    operations = [
        migrations.RunPython(transfer_organization_owner),
    ]
