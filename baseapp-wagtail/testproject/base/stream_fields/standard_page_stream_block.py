from baseapp_wagtail.base.blocks import BannerBlock, CustomRichTextBlock
from wagtail.blocks import StreamBlock

from ..blocks.test_block import TestBlock


class StandardPageStreamBlock(StreamBlock):
    rich_text_block = CustomRichTextBlock(icon="pilcrow")
    banner_block = BannerBlock()
    test_block = TestBlock()
