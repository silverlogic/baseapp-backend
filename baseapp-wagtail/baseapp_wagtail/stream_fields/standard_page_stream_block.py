from wagtail.blocks import StreamBlock

from ..blocks import CustomRichTextBlock


class StandardPageStreamBlock(StreamBlock):
    rich_text_block = CustomRichTextBlock(icon="pilcrow")
