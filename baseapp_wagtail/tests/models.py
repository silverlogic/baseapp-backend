from grapple.models import GraphQLStreamfield
from wagtail.blocks import RichTextBlock, StreamBlock
from wagtail.fields import StreamField

from baseapp_wagtail.base.blocks import BannerBlock, CustomImageBlock
from baseapp_wagtail.base.models import DefaultPageModel


class PageForTests(DefaultPageModel):
    body = StreamField(
        StreamBlock(
            [
                # Medias
                ("custom_image_block", CustomImageBlock()),
                # Base
                ("custom_rich_text_block", RichTextBlock()),
                ("banner_block", BannerBlock()),
            ]
        ),
        verbose_name="Page body",
        blank=True,
        use_json_field=True,
    )

    graphql_fields = [
        *DefaultPageModel.graphql_fields,
        GraphQLStreamfield("body"),
    ]
