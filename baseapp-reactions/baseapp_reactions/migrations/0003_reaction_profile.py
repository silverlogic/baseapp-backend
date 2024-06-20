import django.db.models.deletion
import swapper
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_reactions", "0002_alter_reaction_id"),
        swapper.dependency("baseapp_profiles", "Profile"),
    ]

    operations = [
        migrations.AddField(
            model_name="reaction",
            name="profile",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="reactions",
                to=swapper.get_model_name("baseapp_profiles", "Profile"),
                verbose_name="profile",
            ),
        ),
    ]
