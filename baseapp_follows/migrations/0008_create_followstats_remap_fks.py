import django.db.models.deletion
import swapper
from django.db import migrations, models

from baseapp_core.swappable import get_apps_model


def remap_follows_to_document_ids(apps, schema_editor):
    Follow = get_apps_model(apps, "baseapp_follows", "Follow")
    DocumentId = apps.get_model("baseapp_core", "DocumentId")
    FollowStats = apps.get_model("baseapp_follows", "FollowStats")
    Profile = get_apps_model(apps, "baseapp_profiles", "Profile")
    ContentType = apps.get_model("contenttypes", "ContentType")

    if swapper.is_swapped("baseapp_follows", "Follow"):
        return

    profile_ct = ContentType.objects.get_for_model(Profile)

    # Remap Follow.actor_id and Follow.target_id from Profile PKs to DocumentId PKs
    for follow in Follow.objects.all():
        try:
            actor_doc = DocumentId.objects.get(content_type=profile_ct, object_id=follow.actor_id)
            target_doc = DocumentId.objects.get(content_type=profile_ct, object_id=follow.target_id)
        except DocumentId.DoesNotExist:
            # Skip follows with no matching DocumentId (orphaned data)
            follow.delete()
            continue

        Follow.objects.filter(pk=follow.pk).update(actor_id=actor_doc.pk, target_id=target_doc.pk)

    # Seed FollowStats from current follow data
    doc_ids_as_targets = Follow.objects.values_list("target_id", flat=True).distinct()
    doc_ids_as_actors = Follow.objects.values_list("actor_id", flat=True).distinct()
    all_doc_ids = set(doc_ids_as_targets) | set(doc_ids_as_actors)

    for doc_id in all_doc_ids:
        followers_count = Follow.objects.filter(target_id=doc_id).count()
        following_count = Follow.objects.filter(actor_id=doc_id).count()
        FollowStats.objects.update_or_create(
            target_id=doc_id,
            defaults={
                "followers_count": followers_count,
                "following_count": following_count,
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ("baseapp_core", "0001_initial"),
        ("baseapp_follows", "0007_alter_follow_unique_together"),
    ]

    operations = [
        migrations.CreateModel(
            name="FollowStats",
            fields=[
                (
                    "target",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        primary_key=True,
                        related_name="follow_stats",
                        serialize=False,
                        to="baseapp_core.documentid",
                    ),
                ),
                (
                    "followers_count",
                    models.PositiveIntegerField(default=0, editable=False),
                ),
                (
                    "following_count",
                    models.PositiveIntegerField(default=0, editable=False),
                ),
            ],
            options={
                "verbose_name": "Follow Stats",
                "verbose_name_plural": "Follow Stats",
            },
        ),
        migrations.AlterField(
            model_name="follow",
            name="actor",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="following",
                to="baseapp_core.documentid",
                verbose_name="actor",
            ),
        ),
        migrations.AlterField(
            model_name="follow",
            name="target",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="followers",
                to="baseapp_core.documentid",
                verbose_name="target",
            ),
        ),
        migrations.RunPython(
            remap_follows_to_document_ids,
            migrations.RunPython.noop,
        ),
    ]
