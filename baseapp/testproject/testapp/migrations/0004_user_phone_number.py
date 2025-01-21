from django.db import migrations

import phonenumber_field.modelfields


class Migration(migrations.Migration):

    dependencies = [
        ("testapp", "0003_user_groups_user_is_staff_user_user_permissions"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="phone_number",
            field=phonenumber_field.modelfields.PhoneNumberField(
                blank=True, max_length=128, null=True, region=None, unique=True
            ),
        ),
    ]
