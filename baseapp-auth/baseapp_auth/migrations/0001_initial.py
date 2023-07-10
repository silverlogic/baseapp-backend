# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import django.utils.timezone
from django.contrib.postgres.operations import CITextExtension
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        CITextExtension(),
    ]
