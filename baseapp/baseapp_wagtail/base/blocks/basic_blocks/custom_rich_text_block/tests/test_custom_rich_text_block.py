from wagtail.rich_text import RichText

from baseapp_wagtail.tests.mixins import TestPageContextMixin
from baseapp_wagtail.tests.utils.blocks_helpers import BlocksHelper


class CustomRichTextBlockTests(BlocksHelper, TestPageContextMixin):
    block_type = "custom_rich_text_block"

    def test_rich_text_render_within_api_request(self):
        text = f'<p>Link to <a linktype="page" id="{self.page.id}">Test Page</a></p>'
        self.insert_block(self.page, RichText(text))

        r = self.get_page(self.page)
        blocks = self.get_response_body_blocks(r)

        self.assertEqual(len(blocks), 1)
        self.assertIn(f'href="{self.page.url}"', blocks[0]["value"])
