from wagtail.api.v2.serializers import get_serializer_class
from wagtail.images.blocks import ImageChooserBlock

from baseapp_wagtail.medias.serializers import CustomImageSerializer, ImageSizesField


class CustomImageChooserBlock(ImageChooserBlock):
    def __init__(self, *args, **kwargs):
        self.image_sizes = kwargs.pop("image_sizes", None)
        super().__init__(*args, **kwargs)

    def get_api_representation(self, value, context=None):
        if value:
            return self._serialize_image(value, context)
        else:
            return super().get_api_representation(value, context)

    def _serialize_image(self, image, context):
        serializer_class = get_serializer_class(
            image.__class__,
            ["id", "download_url", "image_sizes"],
            meta_fields=["*"],
            field_serializer_overrides=self._maybe_get_serializer_overrides(),
            base=CustomImageSerializer,
        )
        serializer = serializer_class(context=context)
        return serializer.to_representation(image)

    def _maybe_get_serializer_overrides(self):
        if self.image_sizes:
            return {"image_sizes": ImageSizesField(image_sizes=self.image_sizes, read_only=True)}
        return None
