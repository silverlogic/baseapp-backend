# Generated manually

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('profiles', '0005_profileuserrole_invitation_expires_at_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='profileuserrole',
            name='invitation_last_sent_at',
            field=models.DateTimeField(
                blank=True,
                help_text='When the invitation email was last sent/attempted',
                null=True,
                verbose_name='invitation last sent at',
            ),
        ),
        migrations.AddField(
            model_name='profileuserrole',
            name='invitation_send_attempts',
            field=models.IntegerField(
                default=0,
                help_text='Number of times invitation email send was attempted',
                verbose_name='invitation send attempts',
            ),
        ),
        migrations.AddField(
            model_name='profileuserrole',
            name='invitation_delivery_status',
            field=models.CharField(
                choices=[
                    ('NOT_SENT', 'not sent'),
                    ('SENDING', 'sending'),
                    ('SENT', 'sent'),
                    ('FAILED', 'failed'),
                ],
                default='NOT_SENT',
                help_text='Current delivery status of invitation email',
                max_length=20,
                verbose_name='invitation delivery status',
            ),
        ),
        migrations.AddField(
            model_name='profileuserrole',
            name='invitation_last_send_error',
            field=models.TextField(
                blank=True,
                help_text='Error message from last failed send attempt',
                null=True,
                verbose_name='invitation last send error',
            ),
        ),
        migrations.AddField(
            model_name='profileuserrole',
            name='invitation_last_send_provider_message_id',
            field=models.CharField(
                blank=True,
                help_text='Provider message ID from successful send (if available)',
                max_length=255,
                null=True,
                verbose_name='invitation last send provider message id',
            ),
        ),
    ]
