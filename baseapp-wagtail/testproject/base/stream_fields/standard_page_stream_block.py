from wagtail.blocks import StreamBlock

from baseapp_wagtail.base.blocks import CustomRichTextBlock, BannerBlock

from ..blocks.test_block import TestBlock


class StandardPageStreamBlock(StreamBlock):
    rich_text_block = CustomRichTextBlock(icon="pilcrow")
    banner_block = BannerBlock()
    test_block = TestBlock()
