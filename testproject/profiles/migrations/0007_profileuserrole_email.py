from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("profiles", "0006_profileuserrole_invitation_expires_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="profileuserrole",
            name="email",
            field=models.EmailField(blank=True, max_length=254, null=True, verbose_name="email"),
        ),
    ]
