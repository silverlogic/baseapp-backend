from wagtail.blocks import CharBlock, StructBlock


class TestBlock(StructBlock):
    title = CharBlock(required=True, use_json_field=True, max_length=50)

    class Meta:
        template = "base/blocks/empty.html"
        icon = "placeholder"
