from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_reports", "0005_create_default_report_types_and_transfer_values"),
    ]

    operations = [
        migrations.RemoveField(
            model_name="report",
            name="report_type",
        ),
        migrations.RenameField(
            model_name="report",
            old_name="report_type_fk",
            new_name="report_type",
        ),
    ]
