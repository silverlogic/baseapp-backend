from io import BytesIO

import PIL.Image
from django.core.files.base import ContentFile
from django.core.files.images import ImageFile


def get_test_image_file(filename="test.png", colour="white", size=(640, 480)):
    f = BytesIO()
    image = PIL.Image.new("RGBA", size, colour)
    image.save(f, "PNG")
    return ImageFile(f, name=filename)


def get_test_document_file():
    fake_file = ContentFile(b"A boring example document")
    fake_file.name = "test.txt"
    return fake_file
