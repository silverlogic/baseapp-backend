from __future__ import unicode_literals

from django.db import migrations


def create_template_emails(apps, schema_migration):
    email_template_model = apps.get_model("baseapp_message_templates", "EmailTemplate")
    emails_to_create = [
        {
            "name": "Trial Started",
            "subject": "Welcome! Your Free Trial Starts Today",
            "html_content": """
            <p class="t-h5">Hello,</p>
            <p class="t-body2">Thank you for starting your membership. Enjoy unlimited access to premium on-demand content for {{ trial_days }} days free of charge. After your trial expires, you will be automatically charged for your new subscription.</p>
            <a href="{{ url }}" class="button t-button">Explore</a>
            <p class="t-body2">Thank you.</p>
            """,
        },
        {
            "name": "Trial Ended",
            "subject": "Your Trial Will Expire Soon",
            "html_content": """
            <p class="t-h5">Hello,</p>
            <p class="t-body2">We hope you are enjoying your free trial as a member, but unfortunally your trial period will end in 3 days.</p>
            <p class="t-body2">You will be subscribed to the {{ plan }} Membership automatically in 3 days.</p>
            <p class="t-body2">Thank you.</p>
            """,
        },
    ]

    for email in emails_to_create:
        email_template_model.objects.update_or_create(
            name=email["name"],
            defaults={"subject": email["subject"], "html_content": email["html_content"]},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("baseapp_message_templates", "0001_initial"),
        ("baseapp_payments", "0001_initial"),
    ]

    operations = [migrations.RunPython(create_template_emails, migrations.RunPython.noop)]
