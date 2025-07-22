from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLImage, GraphQLString
from wagtail.blocks import CharBlock, StructBlock
from wagtail.images.blocks import ImageChooserBlock


@register_streamfield_block
class CustomImageBlock(StructBlock):
    graphql_fields = [
        GraphQLImage("image"),
        GraphQLString("alt_text"),
    ]

    def __init__(self, *args, **kwargs):
        required = kwargs.pop("required", False)
        local_blocks = [
            ("image", ImageChooserBlock(required=required)),
            (
                "alt_text",
                CharBlock(
                    required=False,
                    help_text='If this is a <a href="https://www.w3.org/WAI/tutorials/images/decorative/" target="_blank">decorative image</a>, please leave this field blank.',
                ),
            ),
        ]
        super().__init__(local_blocks, *args, **kwargs)

    class Meta:
        icon = "image"
        template = "base/blocks/empty.html"
