from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_profiles", "0008_profileuserrole_invitation_expires_at_and_more"),
    ]

    operations = [
        migrations.AddConstraint(
            model_name="profileuserrole",
            constraint=models.UniqueConstraint(
                fields=["profile", "invited_email"],
                name="unique_profile_invited_email",
                condition=models.Q(invited_email__isnull=False),
            ),
        ),
    ]
