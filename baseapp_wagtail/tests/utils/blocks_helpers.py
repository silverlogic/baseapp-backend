from baseapp_wagtail.tests.utils.graphql_helpers import GraphqlHelper

WAGTAIL_PAGE_FIELDS = """
id
title
pageType
ancestors {
    urlPath
    title
}
... on PageForTests {
    featuredImage {
        ... on CustomImageBlock {
            altText
            image {
                url
                sizes
            }
        }
    }
    body {
        id
        field
        blockType
        ... on RichTextBlock {
            value
        }
        ... on ImageChooserBlock {
            image {
                url
                sizes
            }
        }
        ... on CustomImageBlock {
            altText
            image {
                url
                srcSet
            }
        }
        ... on BannerBlock {
            title
            description
            featuredImage {
                url
                sizes
            }
            imagePosition
        }
    }
}
"""

WAGTAIL_PAGE_QUERY_BY_ID = f"""
query Page($id: ID!) {{
    page(id: $id) {{
        {WAGTAIL_PAGE_FIELDS}
    }}
}}
"""

WAGTAIL_PAGE_QUERY_BY_PATH = f"""
query Page($path: String!) {{
    page(urlPath: $path) {{
        {WAGTAIL_PAGE_FIELDS}
    }}
}}
"""


class BlocksHelper(GraphqlHelper):
    block_type = ""
    block_class = None

    def generate_block(self, data, is_bulk=True):
        if is_bulk:
            block = self.block_class()
            data = block.bulk_to_python([data])[0]
        self.insert_block(self.page, data)

    def insert_block(self, page, block_obj):
        page.body.extend(
            [
                (
                    self.block_type,
                    block_obj,
                ),
            ]
        )
        page.save()

    def get_page(self, page):
        return self.query(
            WAGTAIL_PAGE_QUERY_BY_ID,
            variables={"id": page.id},
        )

    def get_page_by_path(self, page):
        return self.query(
            WAGTAIL_PAGE_QUERY_BY_PATH,
            variables={"path": page.url_path},
        )

    def get_response_body_blocks(self, response):
        body = response.json().get("data", {}).get("page", {}).get("body", [])
        return [block for block in body if block.get("field") == self.block_type]
