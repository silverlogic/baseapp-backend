import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Carries the epic's 0006 + 0007 onto the plugin-architecture initial migration.

    Under the plugin architecture the concrete models moved here from
    baseapp_payments, so those two library migrations had nowhere to land.
    """

    dependencies = [
        migrations.swappable_dependency(settings.BASEAPP_PAYMENTS_CUSTOMER_MODEL),
        ("payments", "0001_initial"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="customer",
            unique_together=set(),
        ),
        migrations.AlterUniqueTogether(
            name="subscription",
            unique_together=set(),
        ),
        migrations.AddField(
            model_name="subscription",
            name="customer",
            field=models.ForeignKey(
                # No rows exist at this point on a fresh install; preserve_default
                # drops the default straight after so the column stays non-null.
                default=1,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="subscriptions",
                to=settings.BASEAPP_PAYMENTS_CUSTOMER_MODEL,
            ),
            preserve_default=False,
        ),
        migrations.RemoveField(
            model_name="subscription",
            name="remote_customer_id",
        ),
    ]
