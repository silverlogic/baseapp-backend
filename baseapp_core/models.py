import os
import uuid

from django.db import models
from django.utils.deconstruct import deconstructible
from django.utils.translation import gettext_lazy as _


class CaseInsensitiveCharField(models.CharField):
    description = _("Case insensitive character")

    def db_type(self, connection):
        return "citext"


class CaseInsensitiveTextField(models.TextField):
    description = _("Case insensitive text")

    def db_type(self, connection):
        return "citext"


class CaseInsensitiveEmailField(CaseInsensitiveTextField, models.EmailField):
    description = _("Case insensitive email address")


@deconstructible
class random_name_in(object):
    def __init__(self, dir):
        self.dir = dir

    def __call__(self, instance, filename):
        ext = filename.split(".")[-1]
        filename = "{}.{}".format(uuid.uuid4(), ext)
        return os.path.join(self.dir, filename)


@deconstructible
class random_dir_in(object):
    """
    Upload a file to a directory with a randomly generated name, but keep the real file name.
    """

    def __init__(self, base_dir):
        self.base_dir = base_dir

    def __call__(self, instance, filename):
        return os.path.join(self.base_dir, str(uuid.uuid4()), filename)
