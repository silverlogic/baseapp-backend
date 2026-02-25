from django import forms
from django.utils.functional import cached_property
from wagtail.blocks import StreamBlock
from wagtail.blocks.stream_block import StreamBlockAdapter
from wagtail.fields import StreamField
from wagtail.telepath import register


class PageBodyStreamField(StreamField):
    @staticmethod
    def create(*args, **kwargs):
        kwargs["verbose_name"] = "Page body"
        kwargs["blank"] = True
        kwargs["use_json_field"] = True
        section_stream_block = SectionStreamBlock(
            [
                ("section_stream_block", *args),
            ]
        )
        return PageBodyStreamField(section_stream_block, **kwargs)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class SectionStreamBlock(StreamBlock):
    pass


class SectionBlockAdapter(StreamBlockAdapter):
    js_constructor = "baseapp_wagtail.stream_blocks.SectionStreamBlock"

    @cached_property
    def media(self):
        streamblock_media = super().media
        return forms.Media(
            js=streamblock_media._js + ["baseapp_wagtail/js/section-stream-block.js"],
            css=streamblock_media._css,
        )


register(SectionBlockAdapter(), SectionStreamBlock)
