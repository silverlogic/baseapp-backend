from django.utils.safestring import mark_safe
from wagtail.blocks import CharBlock, ChoiceBlock, StaticBlock, StructBlock

from baseapp_wagtail.base.blocks.basic_blocks.custom_image_chooser_block import (
    CustomImageChooserBlock,
)
from baseapp_wagtail.base.blocks.basic_blocks.custom_rich_text_block import (
    CustomRichTextBlock,
)

RICH_TEXT_FEATURES = ["bold", "italic", "link", "ul", "hr"]


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

    def get_api_representation(self, value, context=None):
        serialized_data = super().get_api_representation(value, context)
        serialized_data.pop("hr")

        return serialized_data

    class Meta:
        template = "base/blocks/empty.html"
        icon = "image"
