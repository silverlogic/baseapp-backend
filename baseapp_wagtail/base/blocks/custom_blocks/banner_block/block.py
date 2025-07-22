import graphene
from django.utils.safestring import mark_safe
from grapple.helpers import register_streamfield_block
from grapple.models import GraphQLImage, GraphQLRichText, GraphQLString
from wagtail.blocks import (
    CharBlock,
    ChoiceBlock,
    RichTextBlock,
    StaticBlock,
    StructBlock,
)
from wagtail.images.blocks import ImageChooserBlock

from baseapp_wagtail.base.graphql.fields import GraphQLDynamicField

RICH_TEXT_FEATURES = ["bold", "italic", "link", "ul", "hr"]


@register_streamfield_block
class BannerBlock(StructBlock):
    title = CharBlock(required=True, use_json_field=True, max_length=50)
    description = RichTextBlock(
        icon="pilcrow",
        required=False,
        features=RICH_TEXT_FEATURES,
        max_length=255,
    )

    hr = StaticBlock(
        admin_text=mark_safe("<hr />"),
        label=" ",
    )

    featured_image = ImageChooserBlock(label=" ", required=False)
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
        GraphQLString("title", required=True),
        GraphQLRichText("description"),
        GraphQLImage("featured_image"),
        GraphQLDynamicField(
            "image_position",
            graphene.Enum("ImagePosition", [("left", "Left"), ("right", "Right")]),
            required=True,
        ),
    ]

    class Meta:
        template = "base/blocks/empty.html"
        icon = "image"
