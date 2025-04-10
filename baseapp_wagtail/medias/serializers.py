from rest_framework.fields import Field
from wagtail.images.api.v2.serializers import ImageSerializer

DEFAULT_IMAGE_SIZES = {
    "small": "fill-320x320",
    "medium": "fill-768x432",
    "medium_square": "fill-768x768",
    "full": "original",
}


class ImageSizesField(Field):
    def __init__(self, image_sizes=None, **kwargs):
        self.image_sizes = dict(DEFAULT_IMAGE_SIZES)
        self.image_sizes.update(image_sizes or {})
        super().__init__(**kwargs)

    def get_attribute(self, instance):
        return instance

    def to_representation(self, value):
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
