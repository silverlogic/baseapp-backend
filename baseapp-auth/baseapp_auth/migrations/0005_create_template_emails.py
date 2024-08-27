from __future__ import unicode_literals

from django.db import migrations


def create_template_emails(apps, schema_migration):
    email_template_model = apps.get_model("baseapp_message_templates", "EmailTemplate")
    emails_to_create = [
        {
            "name": "Email Verification",
            "subject": "Confirm Your Email Address",
            "html_content": """
            <p class="t-h5">Hello,</p>
            <p class="t-body2 gap-top-3">Great to have you on board! Let's make sure your email is all set. Please confirm your email address by clicking the button below:</p>
            <a href="{{ confirm_url }}" class="button t-button gap-top-3 margin-center">Confirm Email Address</a>
            <p class="t-caption gap-top-3 text-center">
                Didn't sign up?<br />
                No worries, you can safely ignore this email.
            </p>
            """,
            "plain_text_content": """
            Hello,
            Great to have you on board! Let's make sure your email is all set. Please confirm your email address by clicking the button below:
            {{ confirm_url }}
            Didn't sign up?
            No worries, you can safely ignore this email.
            """,
        },
        {
            "name": "Password Reset",
            "subject": "Reset Your Password",
            "html_content": """
            <p class="t-h5">Hello,</p>
            <p class="t-body2 gap-top-3">We received a request to reset the password for your account. If you made this request, please reset your password clicking the button below:</p>
            <a href="{{ reset_url }}" class="button t-button gap-top-3 margin-center">Reset Password</a>
            <p class="t-caption gap-top-3 text-center">If you did not request a password reset, please ignore this email.</p>
            """,
            "plain_text_content": """
            Hello,
            We received a request to reset the password for your account. If you made this request, please reset your password clicking the button below:
            {{ reset_url }}
            If you did not request a password reset, please ignore this email.
            """,
        },
        {
            "name": "Email Address Change Confirmation",
            "subject": "Confirm Your New Email Address",
            "html_content": """
            <p class="t-h5">Hello,</p>
            <p class="t-body2 gap-top-3">We're just a step away from updating your email. Please confirm your new email address by clicking the button below:</p>
            <a href="{{ confirm_url }}" class="button t-button gap-top-3 margin-center">Confirm Email Change</a>
            <p class="t-caption-captiontion gap-top-3 text-center">If you did not request this change you can safely ignore this email.</p>
            """,
            "plain_text_content": """
            Hello,
            We're just a step away from updating your email. Please confirm your new email address by clicking the button below:
            {{ confirm_url }}
            If you did not request this change you can safely ignore this email.
            """,
        },
        {
            "name": "Email Address Change Verification",
            "subject": "Your Email Address Has Been Changed",
            "html_content": """
            <p class="t-h5">Hello,</p>
            <p class="t-body2 gap-top-3">Your email address has been changed to {{ new_email }}. Please click below to confirm your new email address:</p>
            <a href="{{ verify_url }}" class="button t-button gap-top-3 margin-center">Confirm Email Change</a>
            <p class="t-caption gap-top-3 text-center">If you did not initiate this change, please contact our support team as soon as possible.</p>
            """,
            "plain_text_content": """
            Hello,
            Your email address has been changed to {{ new_email }}. Please click below to confirm your new email address:
            {{ verify_url }}
            If you did not initiate this change, please contact our support team as soon as possible.
            """,
        },
        {
            "name": "Superuser Added",
            "subject": "A New Superuser Has Been Added",
            "html_content": """
            <p class="t-h5">Hello Superusers,</p>
            <p class="t-body2 gap-top-3">Please be notified that {{ assignee }} is a superuser now assigned by {{ assigner }}.</p>
            <p class="t-caption gap-top-3 text-center">If this was unexpected, please contact our support team.</p>
            """,
            "plain_text_content": """
            Hello Superusers,
            Please be notified that {{ assignee }} is a superuser now assigned by {{ assigner }}.
            If this was unexpected, please contact our support team.
            """,
        },
        {
            "name": "Superuser Removed",
            "subject": "A New Superuser Has Been Removed",
            "html_content": """
            <p class="t-h5">Hello Superusers,</p>
            <p class="t-body2 gap-top-3">Please be notified that {{ assignee }} has been removed as superuser by {{ assigner }}.</p>
            <p class="t-caption gap-top-3 text-center">If this was unexpected, please contact our support team.</p>
            """,
            "plain_text_content": """
            Hello Superusers,
            Please be notified that {{ assignee }} has been removed as superuser by {{ assigner }}.
            If this was unexpected, please contact our support team.
            """,
        },
        {
            "name": "Password Expired",
            "subject": "Your Password Has Expired",
            "html_content": """
            <p class="t-h5">Hello,</p>
            <p class="t-body2 gap-top-3">Your password has expired. For security reasons, please create a new password clicking the following button:</p>
            <a href="{{ update_password_url }}" class="button t-button gap-top-3 margin-center">Update Password</a>
            """,
            "plain_text_content": """
            Hello,
            Your password has expired. For security reasons, please create a new password clicking the following button:
            {{ update_password_url }}
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
        ("baseapp_auth", "0004_alter_superuserupdatelog_assigner"),
    ]

    operations = [migrations.RunPython(create_template_emails, migrations.RunPython.noop)]
