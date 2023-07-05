# -*- coding: utf-8 -*-
# Generated by Django 1.9.4 on 2016-03-21 19:09
from __future__ import unicode_literals

from django.db import migrations, models

import baseapp_core.models


class Migration(migrations.Migration):
    dependencies = [("baseapp_auth", "0001_initial")]

    operations = [
        migrations.AddField(
            model_name="user", name="is_email_verified", field=models.BooleanField(default=False)
        ),
        migrations.AddField(
            model_name="user",
            name="is_new_email_verified",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="user",
            name="new_email",
            field=baseapp_core.models.CaseInsensitiveEmailField(blank=True, max_length=254),
        ),
    ]
