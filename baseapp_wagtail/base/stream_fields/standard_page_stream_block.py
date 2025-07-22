from wagtail.blocks import RichTextBlock, StreamBlock

from ..blocks import BannerBlock


class StandardPageStreamBlock(StreamBlock):
    rich_text_block = RichTextBlock(icon="pilcrow")
    banner_block = BannerBlock()
