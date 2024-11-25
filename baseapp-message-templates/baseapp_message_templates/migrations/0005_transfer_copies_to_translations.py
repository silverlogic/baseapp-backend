import logging

import swapper
from baseapp_core.swappable import get_apps_model
from django.db import migrations

logger = logging.getLogger(__name__)


class Migration(migrations.Migration):
    def forwards_func(apps, _):
        EmailTemplate = get_apps_model(apps, "baseapp_message_templates", "EmailTemplate")
        TemplateTranslation = get_apps_model(
            apps, "baseapp_message_templates", "TemplateTranslation"
        )
        ContentType = apps.get_model("contenttypes", "ContentType")

        if not swapper.is_swapped(
            "baseapp_message_templates", "TemplateTranslation"
        ) and not swapper.is_swapped("baseapp_message_templates", "EmailTemplate"):
            batch_size = 1000
            for email_template in EmailTemplate.objects.iterator(chunk_size=batch_size):
                target_content_type = ContentType.objects.get_for_model(email_template)
                if TemplateTranslation.objects.filter(
                    target_content_type=target_content_type,
                    target_object_id=email_template.pk,
                    language="en",
                ).exists():
                    continue

                html_content = email_template.html_content or ""
                plain_text_content = email_template.plain_text_content or ""

                TemplateTranslation.objects.create(
                    target_content_type=target_content_type,
                    target_object_id=email_template.pk,
                    language="en",
                    subject=email_template.subject,
                    html_content=html_content,
                    plain_text_content=plain_text_content,
                )

    def reverse_func(apps, _):
        TemplateTranslation = get_apps_model(
            apps, "baseapp_message_templates", "TemplateTranslation"
        )

        if not swapper.is_swapped(
            "baseapp_message_templates", "TemplateTranslation"
        ) and not swapper.is_swapped("baseapp_message_templates", "EmailTemplate"):
            batch_size = 1000
            for translation in TemplateTranslation.objects.filter(language="en").iterator(
                chunk_size=batch_size
            ):
                try:

                    template = translation.target
                    if template is None:
                        continue
                    template.subject = translation.subject
                    template.html_content = translation.html_content
                    template.plain_text_content = translation.plain_text_content

                    template.save(
                        update_fields=[
                            "subject",
                            "html_content",
                            "plain_text_content",
                        ]
                    )
                except Exception as e:
                    logger.error(f"Error processing translation {translation.id}: {e}")

    dependencies = [
        ("baseapp_message_templates", "0004_templatetranslation"),
    ]

    operations = [
        migrations.RunPython(forwards_func, reverse_func),
    ]
