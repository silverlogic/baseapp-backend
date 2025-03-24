from wagtail.blocks import RichTextBlock


class CustomRichTextBlock(RichTextBlock):
    # TODO: (wagtail) convert to graphql.
    def get_api_representation(self, value, context=None):
        if not value:
            return None
        return self.render(value, context=context)
