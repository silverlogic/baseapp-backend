import apps.medias.tests.factories as f
from apps.base.blocks.basic_blocks.banner_block import BannerBlock
from tests.mixins import TestPageContextMixin
from tests.utils.blocks_helpers import BlocksHelper


class BannerBlockTests(BlocksHelper, TestPageContextMixin):
    block_type = "banner_block"
    block_class = BannerBlock

    def test_banner_section_block(self):
        self.generate_block(
            {
                "title": "Banner",
                "description": "Banner description",
                "featured_image": {"image": f.CustomImageFactory().pk},
                "image_position": "left",
            },
        )

        r = self.get_page(self.page)
        block = self.get_response_body_blocks(r)

        self.assertEquals(len(block), 1)
        self.assertEquals(block[0]["value"]["title"], "Banner")
        self.assertEquals(block[0]["value"]["description"], "Banner description\n")
        self.assertEquals(block[0]["value"]["image_position"], "left")
        self.assertIsNotNone(block[0]["value"]["featured_image"])
