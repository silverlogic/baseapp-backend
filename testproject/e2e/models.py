from django.db import models


class Mode(models.Model):
    name = models.CharField(max_length=100, blank=True)
