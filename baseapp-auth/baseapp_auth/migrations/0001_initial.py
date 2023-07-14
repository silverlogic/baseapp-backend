# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.contrib.postgres.operations import CITextExtension
from django.db import migrations


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        CITextExtension(),
    ]
