from django.urls import reverse


class BlocksHelper:
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

    def get_page(self, page, extra_params=None):
        params = {"type": type(page)._meta.app_label + "." + type(page).__name__, "fields": "*"}
        if extra_params:
            params.update(extra_params)
        return self.client.get(
            reverse("baseappwagtailapi_base:pages:detail", args=[page.id]), params
        )

    def get_page_by_path(self, page, extra_params=None):
        url_parts = page.get_url_parts()
        _, _, page_path = url_parts
        params = {"html_path": page_path, "fields": "*"}
        if extra_params:
            params.update(extra_params)
        return self.client.get(reverse("baseappwagtailapi_base:pages:path"), params)

    def get_response_body_blocks(self, response):
        body = response.json().get("body", [])
        return [block for block in body if block.get("type") == self.block_type]
