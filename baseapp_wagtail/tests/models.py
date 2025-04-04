from wagtail.blocks import StreamBlock
from wagtail.fields import StreamField

from baseapp_wagtail.base.blocks import (
    BannerBlock,
    CustomImageBlock,
    CustomImageChooserBlock,
    CustomRichTextBlock,
)
from baseapp_wagtail.base.models import DefaultPageModel


class PageForTests(DefaultPageModel):
    body = StreamField(
        StreamBlock(
            [
                # Medias
                ("custom_image_chooser_block", CustomImageChooserBlock()),
                ("custom_image_block", CustomImageBlock()),
                # Base
                ("custom_rich_text_block", CustomRichTextBlock()),
                ("banner_block", BannerBlock()),
            ]
        ),
        verbose_name="Page body",
        blank=True,
        use_json_field=True,
    )
