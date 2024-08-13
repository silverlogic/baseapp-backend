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
            <p class="-body2">Great to have you on board! Let's make sure your email is all set. Please confirm your email address by clicking the button below:</p>
            <a href="{{ confirm_url }}" class="button t-button">Confirm Email Address</a>
            <p class="caption">
                Didn't sign up?<br />
                No worries, you can safely ignore this email.
            </p>
            """,
        },
        {
            "name": "Password Reset",
            "subject": "Reset Your Password",
            "html_content": """
            <p class="t-h5">Hello,</p>
            <p class="t-body2">We received a request to reset the password for your account. If you made this request, please reset your password clicking the button below:</p>
            <a href="{{ reset_url }}" class="button t-button">Reset Password</a>
            <p class="caption">If you did not request a password reset, please ignore this email.</p>
            """,
        },
        {
            "name": "Email Address Change Confirmation",
            "subject": "Confirm Your New Email Address",
            "html_content": """
            <p class="t-h5">Hello,</p>
            <p class="t-body2">We're just a step away from updating your email. Please confirm your new email address by clicking the button below:</p>
            <a href="{{ confirm_url }}" class="button t-button">Confirm Email Change</a>
            <p class="caption">If you did not request this change you can safely ignore this email.</p>
            """,
        },
        {
            "name": "Email Address Change Verification",
            "subject": "Your Email Address Has Been Changed",
            "html_content": """
            <p class="t-h5">Hello,</p>
            <p class="t-body2">Your email address has been changed to {{ new_email }}. Please click below to confirm your new email address:</p>
            <a href="{{ verify_url }}" class="button t-button">Confirm Email Change</a>
            <p class="caption">If you did not initiate this change, please contact our support team as soon as possible.</p>
            """,
        },
        {
            "name": "Superuser Added",
            "subject": "A New Superuser Has Been Added",
            "html_content": """
            <p class="t-h5">Hello Superusers,</p>
            <p class="t-body2">Please be notified that {{ assignee }} is a superuser now assigned by {{ assigner }}.</p>
            <p class="caption">If this was unexpected, please contact our support team.</p>
            """,
        },
        {
            "name": "Superuser Removed",
            "subject": "A New Superuser Has Been Removed",
            "html_content": """
            <p class="t-h5">Hello Superusers,</p>
            <p class="t-body2">Please be notified that {{ assignee }} has been removed as superuser by {{ assigner }}.</p>
            <p class="caption">If this was unexpected, please contact our support team.</p>
            """,
        },
        {
            "name": "Password Expired",
            "subject": "Your Password Has Expired",
            "html_content": """
            <p class="t-h5">Hello,</p>
            <p class="t-body2">Your password has expired. For security reasons, please create a new password clicking the following button:</p>
            <a href="{{ update_password_url }}" class="button t-button">Update Password</a>
            """,
        },
    ]

    for email in emails_to_create:
        email_template_model.objects.update_or_create(
            name=email["name"],
            defaults={"subject": email["subject"], "html_content": email["html_content"]},
        )


class Migration(migrations.Migration):
    dependencies = [("baseapp_auth", "0004_alter_superuserupdatelog_assigner")]

    operations = [migrations.RunPython(create_template_emails, migrations.RunPython.noop)]
