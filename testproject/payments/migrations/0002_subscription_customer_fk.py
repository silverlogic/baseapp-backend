import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def backfill_customer(apps, schema_editor) -> None:
    """Resolve each Subscription's Customer from the remote_customer_id being dropped.

    The column goes away in the next operation, so this is the only moment the mapping
    still exists. A row that cannot be resolved aborts the migration rather than being
    pointed at an arbitrary customer - silently billing one customer's card for
    another's subscription is worse than a failed deploy.
    """
    Subscription = apps.get_model("payments", "Subscription")
    Customer = apps.get_model(settings.BASEAPP_PAYMENTS_CUSTOMER_MODEL)

    for subscription in Subscription.objects.filter(customer__isnull=True).iterator():
        customer = Customer.objects.filter(
            remote_customer_id=subscription.remote_customer_id
        ).first()
        if customer is None:
            raise RuntimeError(
                "Cannot migrate subscription "
                f"{subscription.remote_subscription_id!r}: no Customer with "
                f"remote_customer_id={subscription.remote_customer_id!r}. Reconcile "
                "that row against Stripe before running this migration."
            )
        subscription.customer = customer
        subscription.save(update_fields=["customer"])


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
        # Has to precede the RemoveField below: the constraint names that column.
        migrations.AlterUniqueTogether(
            name="subscription",
            unique_together=set(),
        ),
        # Nullable first so existing rows survive the add; backfilled, then tightened.
        # An earlier version added this non-null with default=1, which pointed every
        # existing subscription at Customer pk 1 and then dropped the column that said
        # where it should have pointed.
        migrations.AddField(
            model_name="subscription",
            name="customer",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="subscriptions",
                to=settings.BASEAPP_PAYMENTS_CUSTOMER_MODEL,
            ),
        ),
        # Forward-only. Reversing re-adds remote_customer_id as a non-null column with
        # no default, which Postgres rejects on any table that still has rows - so the
        # inverse can never run, and writing one would only look reassuring. Reversal
        # works on an empty table, which is also the only case with nothing to restore.
        migrations.RunPython(backfill_customer, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="subscription",
            name="customer",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="subscriptions",
                to=settings.BASEAPP_PAYMENTS_CUSTOMER_MODEL,
            ),
        ),
        migrations.RemoveField(
            model_name="subscription",
            name="remote_customer_id",
        ),
    ]
