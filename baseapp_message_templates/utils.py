import os
import uuid
from itertools import islice
from typing import Iterator

from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile
from django.core.mail import EmailMessage
from django.utils.deconstruct import deconstructible


@deconstructible
class random_name_in(object):
    def __init__(self, dir):
        self.dir = dir

    def __call__(self, instance, filename):
        ext = filename.split(".")[-1]
        filename = "{}.{}".format(uuid.uuid4(), ext)
        return os.path.join(self.dir, filename)


def attach_files(mail: EmailMessage, attachments):
    for attachment in attachments:
        attachment_file = attachment.file if hasattr(attachment, "file") else attachment
        if isinstance(attachment, TemporaryUploadedFile) or isinstance(
            attachment, InMemoryUploadedFile
        ):
            name = attachment.name
        else:
            name = attachment.filename if hasattr(attachment, "filename") else attachment_file.name

        mail.attach(name, attachment_file.read())


def chunk(it: Iterator, size: int):
    it = iter(it)
    return iter(lambda: tuple(islice(it, size)), ())
