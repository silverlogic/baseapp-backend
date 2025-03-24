from django.utils.safestring import mark_safe
from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLString, GraphQLRichText, GraphQLImage
from wagtail.blocks import CharBlock, ChoiceBlock, StaticBlock, StructBlock

from baseapp_wagtail.base.blocks.basic_blocks.custom_image_chooser_block import (
    CustomImageChooserBlock,
)
from baseapp_wagtail.base.blocks.basic_blocks.custom_rich_text_block import (
    CustomRichTextBlock,
)

RICH_TEXT_FEATURES = ["bold", "italic", "link", "ul", "hr"]


@register_streamfield_block
class BannerBlock(StructBlock):
    title = CharBlock(required=True, use_json_field=True, max_length=50)
    description = CustomRichTextBlock(
        icon="pilcrow",
        required=False,
        features=RICH_TEXT_FEATURES,
        max_length=255,
    )

    hr = StaticBlock(
        admin_text=mark_safe("<hr />"),
        label=" ",
    )

    featured_image = CustomImageChooserBlock(label=" ", required=False)
    image_position = ChoiceBlock(
        choices=[
            ("left", "Left"),
            ("right", "Right"),
        ],
        blank=True,
        required=True,
        default="left",
        label="Image Position",
        help_text="This indicates the position of the image in the desktop view.",
    )

    graphql_fields = [
        GraphQLString("title"),
        GraphQLRichText("description"),
        GraphQLImage("featured_image"),
        GraphQLString("image_position"),
    ]

    class Meta:
        template = "base/blocks/empty.html"
        icon = "image"
