from wagtail.blocks import StreamBlock

from ..blocks import CustomRichTextBlock, BannerBlock


class StandardPageStreamBlock(StreamBlock):
    rich_text_block = CustomRichTextBlock(icon="pilcrow")
    banner_block = BannerBlock()
