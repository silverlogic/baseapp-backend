import baseapp_wagtail.medias.tests.factories as media_factory
from baseapp_wagtail.base.blocks.custom_blocks.banner_block import BannerBlock
from baseapp_wagtail.tests.mixins import TestPageContextMixin
from baseapp_wagtail.tests.utils.blocks_helpers import BlocksHelper


class BannerBlockTests(BlocksHelper, TestPageContextMixin):
    block_type = "banner_block"
    block_class = BannerBlock

    def test_banner_section_block(self):
        self.generate_block(
            {
                "title": "Banner",
                "description": "Banner description",
                "featured_image": media_factory.ImageFactory().pk,
                "image_position": "left",
            },
        )

        r = self.get_page(self.page)
        block = self.get_response_body_blocks(r)

        self.assertEqual(len(block), 1)
        self.assertEqual(block[0]["value"]["title"], "Banner")
        self.assertEqual(block[0]["value"]["description"], "Banner description")
        self.assertEqual(block[0]["value"]["image_position"], "left")
        self.assertIsNotNone(block[0]["value"]["featured_image"])
