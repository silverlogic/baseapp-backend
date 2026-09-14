from typing import TYPE_CHECKING, Any

from rest_framework.fields import Field
from wagtail.images.api.v2.serializers import ImageSerializer

if TYPE_CHECKING:
    from wagtail.images.models import AbstractImage

DEFAULT_IMAGE_SIZES = {
    "small": "fill-320x320",
    "medium": "fill-768x432",
    "medium_square": "fill-768x768",
    "full": "original",
}


class ImageSizesField(Field):
    def __init__(self, image_sizes=None, **kwargs) -> None:
        self.image_sizes = dict(DEFAULT_IMAGE_SIZES)
        self.image_sizes.update(image_sizes or {})
        super().__init__(**kwargs)

    def get_attribute(self, instance) -> "AbstractImage":
        return instance

    def to_representation(self, value) -> dict[str, dict[str, Any]] | None:
        if not value:
            return None

        image_sizes = {}
        for key, size in self.image_sizes.items():
            cropped_img = value.get_rendition(size)
            if cropped_img:
                image_sizes[key] = {
                    "width": cropped_img.width,
                    "height": cropped_img.height,
                    "image_url": cropped_img.full_url,
                }

        return image_sizes if image_sizes else None


class CustomImageSerializer(ImageSerializer):
    image_sizes = ImageSizesField(read_only=True)
