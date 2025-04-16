from wagtail.blocks import StreamBlock
from wagtail.fields import StreamField

from baseapp_wagtail.base.blocks import CustomImageBlock


class FeaturedImageStreamField(StreamField):
    @staticmethod
    def create(*args, **kwargs):
        kwargs.setdefault("verbose_name", "Featured Image")
        kwargs.setdefault("null", True)
        kwargs.setdefault("blank", True)
        kwargs.setdefault("use_json_field", True)

        featured_image_stream_block = FeaturedImageStreamBlock(max_num=1)
        return FeaturedImageStreamField(featured_image_stream_block, **kwargs)


class FeaturedImageStreamBlock(StreamBlock):
    featured_image = CustomImageBlock()
