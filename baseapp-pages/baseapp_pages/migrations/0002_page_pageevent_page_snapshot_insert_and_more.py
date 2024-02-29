import django.db.models.deletion
import django.utils.timezone
import django_quill.fields
import model_utils.fields
import pgtrigger.compiler
import pgtrigger.migrations
import swapper
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("baseapp_pages", "0001_initial"),
        ("pghistory", "0005_events_middlewareevents"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        swapper.dependency("baseapp_pages", "Page"),
    ]

    operations = [
        migrations.CreateModel(
            name="Page",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                (
                    "created",
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now, editable=False, verbose_name="created"
                    ),
                ),
                (
                    "modified",
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now, editable=False, verbose_name="modified"
                    ),
                ),
                (
                    "title_en",
                    models.CharField(blank=True, max_length=255, null=True, verbose_name="title"),
                ),
                (
                    "title_es",
                    models.CharField(blank=True, max_length=255, null=True, verbose_name="title"),
                ),
                (
                    "title_pt",
                    models.CharField(blank=True, max_length=255, null=True, verbose_name="title"),
                ),
                (
                    "body_en",
                    django_quill.fields.QuillField(blank=True, null=True, verbose_name="body"),
                ),
                (
                    "body_es",
                    django_quill.fields.QuillField(blank=True, null=True, verbose_name="body"),
                ),
                (
                    "body_pt",
                    django_quill.fields.QuillField(blank=True, null=True, verbose_name="body"),
                ),
                (
                    "status",
                    models.IntegerField(
                        choices=[(1, "Draft"), (2, "Published")], db_index=True, default=2
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="pages",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="user",
                    ),
                ),
            ],
            options={
                "swappable": swapper.swappable_setting("baseapp_pages", "Page"),
            },
        ),
        migrations.CreateModel(
            name="PageEvent",
            fields=[
                ("pgh_id", models.AutoField(primary_key=True, serialize=False)),
                (
                    "pgh_operation",
                    models.IntegerField(
                        choices=[
                            (1, "Insert"),
                            (2, "Update"),
                            (3, "Delete"),
                            (4, "Insertorupdate"),
                        ],
                        null=True,
                    ),
                ),
                ("pgh_created_at", models.DateTimeField(auto_now_add=True)),
                ("pgh_label", models.TextField(help_text="The event label.")),
                ("id", models.IntegerField()),
                (
                    "created",
                    model_utils.fields.AutoCreatedField(
                        default=django.utils.timezone.now, editable=False, verbose_name="created"
                    ),
                ),
                (
                    "modified",
                    model_utils.fields.AutoLastModifiedField(
                        default=django.utils.timezone.now, editable=False, verbose_name="modified"
                    ),
                ),
                (
                    "title_en",
                    models.CharField(blank=True, max_length=255, null=True, verbose_name="title"),
                ),
                (
                    "title_es",
                    models.CharField(blank=True, max_length=255, null=True, verbose_name="title"),
                ),
                (
                    "title_pt",
                    models.CharField(blank=True, max_length=255, null=True, verbose_name="title"),
                ),
                (
                    "body_en",
                    django_quill.fields.QuillField(blank=True, null=True, verbose_name="body"),
                ),
                (
                    "body_es",
                    django_quill.fields.QuillField(blank=True, null=True, verbose_name="body"),
                ),
                (
                    "body_pt",
                    django_quill.fields.QuillField(blank=True, null=True, verbose_name="body"),
                ),
                (
                    "status",
                    models.IntegerField(choices=[(1, "Draft"), (2, "Published")], default=2),
                ),
                (
                    "pgh_context",
                    models.ForeignKey(
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        to="pghistory.context",
                    ),
                ),
                (
                    "pgh_obj",
                    models.ForeignKey(
                        db_constraint=False,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="event",
                        to=swapper.get_model_name("baseapp_pages", "Page"),
                    ),
                ),
                (
                    "user",
                    models.ForeignKey(
                        blank=True,
                        db_constraint=False,
                        null=True,
                        on_delete=django.db.models.deletion.DO_NOTHING,
                        related_name="+",
                        related_query_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="user",
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="page",
            trigger=pgtrigger.compiler.Trigger(
                name="snapshot_insert",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    func='INSERT INTO "baseapp_pages_pageevent" ("body_en", "body_es", "body_pt", "created", "id", "modified", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "pgh_operation", "status", "title_en", "title_es", "title_pt", "user_id") VALUES (NEW."body_en", NEW."body_es", NEW."body_pt", NEW."created", NEW."id", NEW."modified", _pgh_attach_context(), NOW(), \'snapshot\', NEW."id", 1, NEW."status", NEW."title_en", NEW."title_es", NEW."title_pt", NEW."user_id"); RETURN NULL;',
                    hash="47d0c72ae65dffb33b1c76dd778ade76385ffd10",
                    operation="INSERT",
                    pgid="pgtrigger_snapshot_insert_f0c08",
                    table="baseapp_pages_page",
                    when="AFTER",
                ),
            ),
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="page",
            trigger=pgtrigger.compiler.Trigger(
                name="snapshot_update",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    condition="WHEN (OLD.* IS DISTINCT FROM NEW.*)",
                    func='INSERT INTO "baseapp_pages_pageevent" ("body_en", "body_es", "body_pt", "created", "id", "modified", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "pgh_operation", "status", "title_en", "title_es", "title_pt", "user_id") VALUES (NEW."body_en", NEW."body_es", NEW."body_pt", NEW."created", NEW."id", NEW."modified", _pgh_attach_context(), NOW(), \'snapshot\', NEW."id", 2, NEW."status", NEW."title_en", NEW."title_es", NEW."title_pt", NEW."user_id"); RETURN NULL;',
                    hash="16d01d32a1f7425139d8108971ac5beb1460f192",
                    operation="UPDATE",
                    pgid="pgtrigger_snapshot_update_845c1",
                    table="baseapp_pages_page",
                    when="AFTER",
                ),
            ),
        ),
        pgtrigger.migrations.AddTrigger(
            model_name="page",
            trigger=pgtrigger.compiler.Trigger(
                name="snapshot_delete",
                sql=pgtrigger.compiler.UpsertTriggerSql(
                    func='INSERT INTO "baseapp_pages_pageevent" ("body_en", "body_es", "body_pt", "created", "id", "modified", "pgh_context_id", "pgh_created_at", "pgh_label", "pgh_obj_id", "pgh_operation", "status", "title_en", "title_es", "title_pt", "user_id") VALUES (OLD."body_en", OLD."body_es", OLD."body_pt", OLD."created", OLD."id", OLD."modified", _pgh_attach_context(), NOW(), \'snapshot\', OLD."id", 3, OLD."status", OLD."title_en", OLD."title_es", OLD."title_pt", OLD."user_id"); RETURN NULL;',
                    hash="c086d17f4aa1d886fb228a59fd016bdf81a4005e",
                    operation="DELETE",
                    pgid="pgtrigger_snapshot_delete_caf3a",
                    table="baseapp_pages_page",
                    when="AFTER",
                ),
            ),
        ),
    ]
