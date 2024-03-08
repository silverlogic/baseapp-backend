import phonenumber_field.modelfields
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("testapp", "0007_user_groups_user_is_staff_user_user_permissions"),
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
