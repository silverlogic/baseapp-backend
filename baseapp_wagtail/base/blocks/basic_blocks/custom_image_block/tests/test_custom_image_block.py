import baseapp_wagtail.medias.tests.factories as f
from baseapp_wagtail.tests.mixins import TestPageContextMixin
from baseapp_wagtail.tests.utils.blocks_helpers import BlocksHelper


class CustomImageBlockTests(BlocksHelper, TestPageContextMixin):
    block_type = "custom_image_block"

    def setUp(self):
        self.image = f.ImageFactory()

    def test_custom_image_block(self):
        self.insert_block(self.page, {"image": self.image, "alt_text": "Test alt text"})

        r = self.get_page(self.page)
        blocks = self.get_response_body_blocks(r)

        self.assertEqual(len(blocks), 1)
        self.assertIsNotNone(blocks[0]["value"]["image"])
        self.assertEqual(blocks[0]["value"]["alt_text"], "Test alt text")
