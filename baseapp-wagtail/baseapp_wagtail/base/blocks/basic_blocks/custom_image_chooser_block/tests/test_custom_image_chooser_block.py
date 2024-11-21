import baseapp_wagtail.medias.tests.factories as f
from baseapp_wagtail.base.blocks.basic_blocks.custom_image_chooser_block.block import (
    CustomImageChooserBlock,
)
from baseapp_wagtail.medias.serializers import DEFAULT_IMAGE_SIZES
from baseapp_wagtail.tests.mixins import TestPageContextMixin
from baseapp_wagtail.tests.utils.blocks_helpers import BlocksHelper


class CustomImageChooserBlockTests(BlocksHelper, TestPageContextMixin):
    block_type = "custom_image_chooser_block"

    def setUp(self):
        self.image = f.ImageFactory()

    def test_image_selection(self):
        self.insert_block(self.page, self.image)
        r = self.get_page(self.page)
        blocks = self.get_response_body_blocks(r)

        self.assertEqual(len(blocks), 1)
        self.assertEqual(blocks[0]["value"]["id"], self.image.id)
        self.assertEqual(blocks[0]["value"]["image_sizes"].keys(), DEFAULT_IMAGE_SIZES.keys())

    def test_image_selection_with_image_sizes(self):
        block = CustomImageChooserBlock(image_sizes={"test": "fill-100x100"})
        data = block.get_api_representation(self.image, context=None)

        self.assertEqual(data["id"], self.image.id)
        self.assertEqual(
            list(data["image_sizes"].keys()), list(DEFAULT_IMAGE_SIZES.keys()) + ["test"]
        )
