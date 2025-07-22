from wagtail.blocks import RichTextBlock, StreamBlock

from baseapp_wagtail.base.blocks import BannerBlock

from ..blocks.test_block import TestBlock


class StandardPageStreamBlock(StreamBlock):
    rich_text_block = RichTextBlock(icon="pilcrow")
    banner_block = BannerBlock()
    test_block = TestBlock()
