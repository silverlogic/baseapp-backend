from wagtail.blocks import StreamBlock

from baseapp_wagtail.blocks import CustomImageBlock


class FeaturedImageStreamBlock(StreamBlock):
    featured_image = CustomImageBlock()
